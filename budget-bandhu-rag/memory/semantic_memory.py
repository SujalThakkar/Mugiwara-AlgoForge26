"""
memory/semantic_memory.py — Tier 3: Persistent user profile facts on Atlas.

Stores attribute:value facts about a user with:
  - Bayesian-style confidence upsert (confirmed_count momentum)
  - Atlas $search for BM25 text retrieval
  - Auto-embedding on write for future vector expansion
  - confirmed_count-weighted retrieval ordering

Collection: semantic_memory
Index: semantic_text_index (Atlas Search on 'attribute', 'value')

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import logging
import os
import pickle
import uuid
from datetime import datetime
from typing import Callable, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from models.schemas import SemanticMemory

logger = logging.getLogger(__name__)

_COLLECTION = "semantic_memory"
_TEXT_INDEX = "semantic_text_index"
_BAYESIAN_ALPHA = 0.3   # blending factor: new_conf = alpha * new + (1-alpha) * old


class SemanticMemoryStore:
    """
    Atlas-backed Tier 3 semantic / profile memory.

    Usage:
        store = SemanticMemoryStore(db, embedding_fn)
        await store.upsert_fact(user_id, "INCOME_RANGE", "monthly_income", "Rs.50000")
        profile = await store.get_profile("user-1")
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        embedding_fn: Optional[Callable] = None,
    ):
        self._col   = db[_COLLECTION]
        self._embed = embedding_fn

    # ──────────────────────────────────────────────────────────────────────────
    # WRITES
    # ──────────────────────────────────────────────────────────────────────────

    async def upsert_fact(
        self,
        user_id: str,
        memory_type: str,
        attribute: str,
        value: str,
        confidence: float = 0.5,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Insert or update a semantic profile fact with Bayesian confidence blending.

        If the fact already exists:
          - confirmed_count += 1
          - new_confidence = 0.3 * incoming + 0.7 * existing (blended)
          - value updated to latest observation

        Args:
            user_id: User identifier.
            memory_type: Category (INCOME_RANGE, GOAL, RISK_PROFILE, PREFERENCE, ...).
            attribute: Fact key (e.g., "monthly_income", "risk_appetite").
            value: Fact value (e.g., "Rs.50000", "moderate").
            confidence: Incoming confidence score.
            session_id: Source session.

        Returns:
            Document ID (upserted or existing).

        Example:
            >>> fid = await store.upsert_fact(
            ...     "user-1", "INCOME_RANGE", "monthly_income", "Rs.50000", 0.8
            ... )
        """
        fact_id  = str(uuid.uuid4())
        now      = datetime.utcnow()
        text_for_embed = f"{attribute} {value}"

        # Generate embedding
        embedding: Optional[List[float]] = None
        if self._embed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                vec  = await loop.run_in_executor(None, self._embed, text_for_embed)
                embedding = vec.tolist() if hasattr(vec, "tolist") else list(vec)
            except Exception:
                pass

        # Bayesian-blended confidence update on existing doc
        bayesian_update_pipeline = [
            {
                "$set": {
                    "value"          : value,
                    "confidence_score": {
                        "$add": [
                            {"$multiply": [_BAYESIAN_ALPHA, confidence]},
                            {"$multiply": [1 - _BAYESIAN_ALPHA, "$confidence_score"]},
                        ]
                    },
                    "confirmed_count": {"$add": ["$confirmed_count", 1]},
                    "last_updated"   : now,
                }
            }
        ]

        filter_doc = {"user_id": user_id, "attribute": attribute}

        try:
            result = await self._col.find_one_and_update(
                filter_doc,
                bayesian_update_pipeline,
                return_document=True,
                upsert=False,
            )

            if result is None:
                # First time this attribute is seen — insert fresh
                doc = {
                    "id"              : fact_id,
                    "user_id"         : user_id,
                    "memory_type"     : memory_type,
                    "attribute"       : attribute,
                    "value"           : value,
                    "embedding"       : embedding,
                    "confidence_score": confidence,
                    "confirmed_count" : 1,
                    "source_session_ids": [session_id] if session_id else [],
                    "last_updated"    : now,
                    "created_at"      : now,
                }
                insert_result = await self._col.insert_one(doc)
                return str(insert_result.inserted_id)

            if session_id and session_id not in result.get("source_session_ids", []):
                await self._col.update_one(
                    {"_id": result["_id"]},
                    {"$addToSet": {"source_session_ids": session_id}},
                )

            return str(result.get("_id", fact_id))

        except Exception as exc:
            logger.error(f"[SEMANTIC] Upsert failed: {exc}")
            raise

    async def bulk_upsert(
        self, user_id: str, facts: List[dict], session_id: Optional[str] = None
    ) -> int:
        """
        Upsert multiple facts efficiently via bulk_write.

        Args:
            user_id: User identifier.
            facts: List of dicts with keys: memory_type, attribute, value, confidence.
            session_id: Source session.

        Returns:
            Number of facts upserted.

        Example:
            >>> n = await store.bulk_upsert("user-1", [
            ...     {"memory_type": "INCOME_RANGE", "attribute": "monthly_income",
            ...      "value": "Rs.50000", "confidence": 0.9}
            ... ])
        """
        if not facts:
            return 0

        ops = []
        for f in facts:
            ops.append(
                UpdateOne(
                    {"user_id": user_id, "attribute": f["attribute"]},
                    {
                        "$set"     : {"value": f["value"], "last_updated": datetime.utcnow()},
                        "$inc"     : {"confirmed_count": 1},
                        "$setOnInsert": {
                            "id"              : str(uuid.uuid4()),
                            "user_id"         : user_id,
                            "memory_type"     : f.get("memory_type", "UNKNOWN"),
                            "confidence_score": f.get("confidence", 0.5),
                            "created_at"      : datetime.utcnow(),
                        },
                    },
                    upsert=True,
                )
            )

        try:
            result = await self._col.bulk_write(ops, ordered=False)
            return result.upserted_count + result.modified_count
        except Exception as exc:
            logger.warning(f"[SEMANTIC] Bulk upsert error: {exc}")
            return 0

    # ──────────────────────────────────────────────────────────────────────────
    # READS
    # ──────────────────────────────────────────────────────────────────────────

    async def get_profile(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[SemanticMemory]:
        """
        Return all semantic facts for a user, ordered by confirmed_count DESC.

        Args:
            user_id: User to retrieve profile for.
            limit: Maximum number of facts.

        Returns:
            List of SemanticMemory with highest-confidence facts first.

        Example:
            >>> facts = await store.get_profile("user-1")
            >>> facts[0].attribute
            'monthly_income'
        """
        try:
            cursor = (
                self._col.find({"user_id": user_id})
                .sort([("confirmed_count", -1), ("confidence_score", -1)])
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return [_doc_to_semantic(d) for d in docs]
        except Exception as exc:
            logger.error(f"[SEMANTIC] Profile fetch failed: {exc}")
            return []

    async def retrieve(
        self,
        user_id: str,
        limit: int = 20,
        query_embedding: Optional[object] = None,
    ) -> List[SemanticMemory]:
        """Alias for get_profile() — backward-compatible interface."""
        return await self.get_profile(user_id, limit)

    async def text_search(
        self,
        query_text: str,
        user_id: str,
        k: int = 10,
    ) -> List[SemanticMemory]:
        """
        Atlas $search BM25 retrieval over attribute + value fields.

        Args:
            query_text: Natural language query.
            user_id: User filter.
            k: Maximum results.

        Returns:
            Best-matching semantic facts, BM25-ranked.

        Example:
            >>> facts = await store.text_search("monthly income salary", "user-1")
        """
        pipeline = [
            {
                "$search": {
                    "index": _TEXT_INDEX,
                    "text" : {
                        "query": query_text,
                        "path" : ["attribute", "value"],
                    },
                }
            },
            {"$match": {"user_id": user_id}},
            {"$limit": k},
            {"$addFields": {"_text_score": {"$meta": "searchScore"}}},
        ]
        try:
            cursor = self._col.aggregate(pipeline)
            docs   = await cursor.to_list(length=k)
            return [_doc_to_semantic(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[SEMANTIC] Text search failed: {exc}")
            # Fallback to confirmed_count sort
            return await self.retrieve(user_id, limit=k)

    async def get_fact(
        self, user_id: str, attribute: str
    ) -> Optional[SemanticMemory]:
        """
        Get a single semantic fact by attribute key.

        Args:
            user_id: User identifier.
            attribute: Fact key to look up.

        Returns:
            SemanticMemory if found, None otherwise.

        Example:
            >>> fact = await store.get_fact("user-1", "monthly_income")
            >>> fact.value
            'Rs.50000'
        """
        try:
            doc = await self._col.find_one({"user_id": user_id, "attribute": attribute})
            return _doc_to_semantic(doc) if doc else None
        except Exception as exc:
            logger.warning(f"[SEMANTIC] get_fact failed: {exc}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_semantic(doc: dict) -> SemanticMemory:
    """Convert Atlas document dict to SemanticMemory Pydantic model."""
    emb = doc.get("embedding")
    emb_bytes: Optional[bytes] = None
    if emb and isinstance(emb, list):
        emb_bytes = pickle.dumps(emb)

    return SemanticMemory(
        id               = doc.get("id", str(doc.get("_id", ""))),
        user_id          = doc["user_id"],
        memory_type      = doc.get("memory_type", "UNKNOWN"),
        attribute        = doc.get("attribute", ""),
        value            = doc.get("value", ""),
        embedding        = emb_bytes,
        confidence_score = float(doc.get("confidence_score", 0.5)),
        confirmed_count  = int(doc.get("confirmed_count", 0)),
        source_session_ids = doc.get("source_session_ids", []),
        last_updated     = doc.get("last_updated", datetime.utcnow()),
        created_at       = doc.get("created_at", datetime.utcnow()),
    )
