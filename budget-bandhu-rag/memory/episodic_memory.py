"""
memory/episodic_memory.py — Tier 2: Event-based memory on MongoDB Atlas.

Stores financial life events with:
  - Auto-embedding on write (384-dim all-MiniLM-L6-v2)
  - $vectorSearch for semantic similarity retrieval
  - $search (BM25) for keyword retrieval
  - hybrid_search() merges both via RRF
  - Daily decay: decay_score *= 0.95^days_since_last_reinforced

Collection: episodic_memory
Index requirements (Atlas UI / mongocli):
  - episodic_vector_index: vector search on 'embedding', 384-dim, cosine
  - episodic_text_index: full-text on trigger_description, outcome_description, category

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import os
import pickle
import uuid
from datetime import datetime, timedelta
from typing import Callable, List, Optional

import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import EpisodicMemory, UserReaction

logger = logging.getLogger(__name__)

_COLLECTION    = "episodic_memory"
_VECTOR_INDEX  = os.getenv("ATLAS_VECTOR_INDEX_NAME", "episodic_vector_index")
_TEXT_INDEX    = os.getenv("ATLAS_TEXT_INDEX_NAME",   "episodic_text_index")
_EMBED_DIM     = 384
_DECAY_FACTOR  = 0.95
_RRF_K         = 60


class EpisodicMemoryStore:
    """
    Atlas-backed Tier 2 episodic memory.

    Usage:
        store = EpisodicMemoryStore(db, embedding_fn)
        ep_id = await store.store_episode(user_id, "OVERSPEND", "Spent on Zomato", "₹2,000")
        results = await store.hybrid_search(q_emb, "food spending", user_id, k=5)
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        embedding_fn: Optional[Callable] = None,
    ):
        self._col    = db[_COLLECTION]
        self._embed  = embedding_fn

    # ──────────────────────────────────────────────────────────────────────────
    # WRITES
    # ──────────────────────────────────────────────────────────────────────────

    async def store_episode(
        self,
        user_id: str,
        event_type: str,
        trigger_description: str,
        outcome_description: str = "",
        session_id: Optional[str] = None,
        category: Optional[str] = None,
        amount_inr: Optional[float] = None,
        confidence_score: float = 0.5,
        user_reaction: str = UserReaction.UNKNOWN,
    ) -> str:
        """
        Store a financial event as an episodic memory in Atlas.

        Auto-embeds trigger + outcome text for vector search.

        Args:
            user_id: User identifier.
            event_type: Event class (OVERSPEND, SUCCESS, CORRECTION, ANOMALY, ...).
            trigger_description: What happened (the event).
            outcome_description: Result or advice given.
            session_id: Session that produced this event.
            category: Spending category if applicable.
            amount_inr: Amount in Indian Rupees if applicable.
            confidence_score: Initial confidence (0-1).
            user_reaction: How the user responded.

        Returns:
            Inserted document ID string.

        Example:
            >>> ep_id = await store.store_episode(
            ...     "user-1", "OVERSPEND",
            ...     "Spent Rs.3000 on dining this weekend",
            ...     "Advised to set weekly dining cap",
            ...     category="food", amount_inr=3000.0
            ... )
        """
        ep_id = str(uuid.uuid4())
        now   = datetime.utcnow()

        # Generate embedding
        embedding: Optional[List[float]] = None
        if self._embed:
            text_to_embed = f"{trigger_description} {outcome_description}".strip()
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                vec  = await loop.run_in_executor(None, self._embed, text_to_embed)
                embedding = _to_float_list(vec)
            except Exception as exc:
                logger.warning(f"[EPISODIC] Embedding failed (storing without): {exc}")

        doc = {
            "id"                  : ep_id,
            "user_id"             : user_id,
            "session_id"          : session_id,
            "event_type"          : event_type,
            "trigger_description" : trigger_description,
            "outcome_description" : outcome_description,
            "user_reaction"       : user_reaction,
            "category"            : category,
            "amount_inr"          : amount_inr,
            "embedding"           : embedding,   # List[float], 384-dim
            "confidence_score"    : confidence_score,
            "decay_score"         : 1.0,
            "reinforcement_count" : 0,
            "created_at"          : now,
            "last_reinforced"     : now,
        }

        try:
            await self._col.insert_one(doc)
        except Exception as exc:
            logger.error(f"[EPISODIC] Insert failed: {exc}")
            raise

        return ep_id

    async def reinforce(self, episode_id: str, user_id: str) -> None:
        """
        Reinforce an episodic memory: reset decay_score=1.0, increment count.

        Args:
            episode_id: Episode 'id' field value.
            user_id: Owner (for safety filter).

        Example:
            >>> await store.reinforce("ep-uuid", "user-1")
        """
        try:
            await self._col.update_one(
                {"id": episode_id, "user_id": user_id},
                {
                    "$set": {"decay_score": 1.0, "last_reinforced": datetime.utcnow()},
                    "$inc": {"reinforcement_count": 1},
                },
            )
        except Exception as exc:
            logger.warning(f"[EPISODIC] Reinforce failed: {exc}")

    async def apply_decay(self, user_id: str) -> int:
        """
        Apply daily decay to all of a user's episodic memories.

        decay_score = max(0.01, decay_score * 0.95^days_since_last_reinforced)

        Implemented as a MongoDB aggregation update to avoid Python loops.
        M0-safe: no transactions, bulk update via $set with computed expression.

        Args:
            user_id: User whose memories to decay.

        Returns:
            Number of documents updated.

        Example:
            >>> updated = await store.apply_decay("user-1")
        """
        try:
            now       = datetime.utcnow()
            threshold = now - timedelta(hours=1)  # Only decay if not reinforced today

            result = await self._col.update_many(
                {
                    "user_id"      : user_id,
                    "last_reinforced": {"$lt": threshold},
                    "decay_score"  : {"$gt": 0.01},
                },
                [
                    {
                        "$set": {
                            "decay_score": {
                                "$max": [
                                    0.01,
                                    {
                                        "$multiply": [
                                            "$decay_score",
                                            {
                                                "$pow": [
                                                    _DECAY_FACTOR,
                                                    {
                                                        "$divide": [
                                                            {"$subtract": [now, "$last_reinforced"]},
                                                            86_400_000,  # ms per day
                                                        ]
                                                    },
                                                ]
                                            },
                                        ]
                                    },
                                ]
                            }
                        }
                    }
                ],
            )
            return result.modified_count
        except Exception as exc:
            logger.warning(f"[EPISODIC] Decay update failed: {exc}")
            return 0

    # ──────────────────────────────────────────────────────────────────────────
    # READS — VECTOR SEARCH
    # ──────────────────────────────────────────────────────────────────────────

    async def vector_search(
        self,
        query_embedding: List[float],
        user_id: str,
        k: int = 10,
        min_decay_score: float = 0.1,
    ) -> List[EpisodicMemory]:
        """
        Atlas $vectorSearch aggregation — HNSW cosine similarity.

        Args:
            query_embedding: 384-dim float list.
            user_id: Filter to this user's memories only.
            k: Maximum results.
            min_decay_score: Exclude heavily-decayed memories.

        Returns:
            List of EpisodicMemory sorted by vector score DESC.

        Example:
            >>> results = await store.vector_search(q_emb, "user-1", k=8)
        """
        pipeline = [
            {
                "$vectorSearch": {
                    "index"        : _VECTOR_INDEX,
                    "path"         : "embedding",
                    "queryVector"  : query_embedding,
                    "numCandidates": k * 5,
                    "limit"        : k,
                    "filter"       : {
                        "user_id"    : user_id,
                        "decay_score": {"$gte": min_decay_score},
                    },
                }
            },
            {
                "$addFields": {"_vector_score": {"$meta": "vectorSearchScore"}}
            },
        ]
        return await self._run_pipeline(pipeline)

    # ──────────────────────────────────────────────────────────────────────────
    # READS — TEXT SEARCH (BM25 via Atlas Search)
    # ──────────────────────────────────────────────────────────────────────────

    async def text_search(
        self,
        query_text: str,
        user_id: str,
        k: int = 10,
    ) -> List[EpisodicMemory]:
        """
        Atlas $search BM25 full-text retrieval via Lucene.

        Args:
            query_text: Natural language query.
            user_id: User to filter by.
            k: Maximum results.

        Returns:
            List of EpisodicMemory sorted by BM25 relevance DESC.

        Example:
            >>> results = await store.text_search("food dining overspend", "user-1")
        """
        pipeline = [
            {
                "$search": {
                    "index": _TEXT_INDEX,
                    "text" : {
                        "query": query_text,
                        "path" : ["trigger_description", "outcome_description", "category"],
                    },
                }
            },
            {"$match": {"user_id": user_id, "decay_score": {"$gte": 0.1}}},
            {"$limit": k},
            {"$addFields": {"_text_score": {"$meta": "searchScore"}}},
        ]
        return await self._run_pipeline(pipeline)

    # ──────────────────────────────────────────────────────────────────────────
    # READS — HYBRID (VECTOR + TEXT, RRF MERGED)
    # ──────────────────────────────────────────────────────────────────────────

    async def hybrid_search(
        self,
        query_embedding: Optional[List[float]],
        query_text: str,
        user_id: str,
        k: int = 10,
    ) -> List[EpisodicMemory]:
        """
        Run vector + text search in parallel and merge via RRF.

        Atlas does NOT support $vectorSearch and $search in the same pipeline.
        We run both as separate aggregations via asyncio.gather().

        Args:
            query_embedding: 384-dim float list (None → skip vector search).
            query_text: BM25 query string.
            user_id: User to filter by.
            k: Final top-k after merge.

        Returns:
            RRF-merged list of EpisodicMemory, up to k results.

        Example:
            >>> results = await store.hybrid_search(q_emb, "food trend", "user-1", k=8)
        """
        import asyncio

        tasks = []
        if query_embedding:
            tasks.append(self.vector_search(query_embedding, user_id, k=k * 2))
        else:
            tasks.append(asyncio.coroutine(lambda: [])())

        tasks.append(self.text_search(query_text, user_id, k=k * 2))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        vector_results = results[0] if not isinstance(results[0], Exception) else []
        text_results   = results[1] if not isinstance(results[1], Exception) else []

        return _rrf_merge_episodes([vector_results, text_results], k)

    # ──────────────────────────────────────────────────────────────────────────
    # READS — SIMPLE (no vector search required)
    # ──────────────────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        user_id: str,
        limit: int = 10,
        event_type: Optional[str] = None,
        min_decay: float = 0.1,
        query_embedding: Optional[object] = None,
    ) -> List[EpisodicMemory]:
        """
        Retrieve recent/highest-decay episodes without $vectorSearch.

        Fallback retrieval used when no embedding is available.

        Args:
            user_id: User to retrieve for.
            limit: Maximum number of results.
            event_type: Optional filter by event type.
            min_decay: Minimum decay_score threshold.
            query_embedding: Ignored (signature compatibility with old interface).

        Returns:
            List of EpisodicMemory sorted by decay_score DESC.

        Example:
            >>> eps = await store.retrieve("user-1", limit=5)
        """
        flt: dict = {"user_id": user_id, "decay_score": {"$gte": min_decay}}
        if event_type:
            flt["event_type"] = event_type

        try:
            cursor = self._col.find(flt).sort("decay_score", -1).limit(limit)
            docs   = await cursor.to_list(length=limit)
            return [_doc_to_episode(d) for d in docs]
        except Exception as exc:
            logger.error(f"[EPISODIC] Retrieve failed: {exc}")
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    async def _run_pipeline(self, pipeline: list) -> List[EpisodicMemory]:
        """Execute an aggregation pipeline and deserialise results."""
        try:
            cursor = self._col.aggregate(pipeline)
            docs   = await cursor.to_list(length=100)
            return [_doc_to_episode(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[EPISODIC] Pipeline error: {exc}")
            return []


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_episode(doc: dict) -> EpisodicMemory:
    """Convert an Atlas document to EpisodicMemory Pydantic model."""
    emb = doc.get("embedding")
    emb_bytes: Optional[bytes] = None
    if emb and isinstance(emb, list):
        emb_bytes = pickle.dumps(emb)   # match legacy bytes interface expected by CRAG

    return EpisodicMemory(
        id                  = doc.get("id", str(doc.get("_id", ""))),
        user_id             = doc["user_id"],
        session_id          = doc.get("session_id"),
        event_type          = doc.get("event_type", "UNKNOWN"),
        trigger_description = doc.get("trigger_description", ""),
        outcome_description = doc.get("outcome_description", ""),
        user_reaction       = doc.get("user_reaction", UserReaction.UNKNOWN),
        category            = doc.get("category"),
        amount_inr          = doc.get("amount_inr"),
        embedding           = emb_bytes,
        confidence_score    = float(doc.get("confidence_score", 0.5)),
        decay_score         = float(doc.get("decay_score", 1.0)),
        reinforcement_count = int(doc.get("reinforcement_count", 0)),
        created_at          = _parse_dt(doc.get("created_at")),
        last_reinforced     = _parse_dt(doc.get("last_reinforced")),
    )


def _to_float_list(vec: object) -> List[float]:
    """Convert numpy array or list to plain Python float list for Atlas."""
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return list(float(x) for x in vec)


def _parse_dt(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _rrf_merge_episodes(
    lists: List[List[EpisodicMemory]],
    k: int,
    rrf_k: int = _RRF_K,
) -> List[EpisodicMemory]:
    """Reciprocal Rank Fusion merge across result lists."""
    from collections import defaultdict
    scores: dict = defaultdict(float)
    ep_map: dict = {}

    for result_list in lists:
        for rank, ep in enumerate(result_list):
            scores[ep.id] += 1.0 / (rank + rrf_k)
            ep_map[ep.id]  = ep

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [ep_map[eid] for eid, _ in ranked[:k]]
