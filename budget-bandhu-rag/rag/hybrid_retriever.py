"""
rag/hybrid_retriever.py — Atlas-native retrieval replacing FAISS + BM25 + NetworkX.

Runs 3 parallel Atlas aggregation pipelines:
  1. $vectorSearch  — HNSW cosine similarity (episodic embeddings)
  2. $search        — Lucene BM25 full-text (episodic + semantic)
  3. $graphLookup   — 2-hop knowledge graph traversal

All 3 execute via asyncio.gather() — parallel, non-blocking.
Results merged via Reciprocal Rank Fusion (RRF, k=60).

PUBLIC INTERFACE IS UNCHANGED from the original FAISS/BM25 version:
  retrieve(query, user_id, tiers, top_k) → list[RetrievedChunk]

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import MemoryTier, RetrievedChunk

logger = logging.getLogger(__name__)

_VECTOR_INDEX  = os.getenv("ATLAS_VECTOR_INDEX_NAME", "episodic_vector_index")
_TEXT_INDEX_EP = os.getenv("ATLAS_TEXT_INDEX_NAME",   "episodic_text_index")
_TEXT_INDEX_SM = "semantic_text_index"
_RRF_K         = 60
_MIN_DECAY     = 0.10


class HybridRetriever:
    """
    Atlas-native hybrid retriever.

    Replaces:
      FAISS         → Atlas $vectorSearch (HNSW, cosine, 384-dim)
      rank_bm25     → Atlas $search (Lucene BM25)
      NetworkX      → Atlas $graphLookup (maxDepth=2)

    Usage:
        retriever = HybridRetriever(atlas_db, embedding_fn)
        chunks = await retriever.retrieve("food spending trend", "user-1", [1,2,3], top_k=10)
    """

    def __init__(
        self,
        atlas_db: AsyncIOMotorDatabase,
        embedding_fn: Optional[Callable] = None,
    ):
        self._db    = atlas_db
        self._embed = embedding_fn

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC INTERFACE (unchanged from FAISS version)
    # ──────────────────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        user_id: str,
        tiers: Optional[List[int]] = None,
        top_k: int = 10,
    ) -> List[RetrievedChunk]:
        """
        Multi-source retrieval via Atlas aggregation pipelines.

        Args:
            query: Natural language query string.
            user_id: User to retrieve documents for.
            tiers: Tier numbers to include (1=Working, 2=Episodic, etc.).
                   None = all applicable tiers.
            top_k: Final number of chunks after RRF merge.

        Returns:
            RRF-merged list of RetrievedChunk, sorted by score DESC.
            Returns empty list if Atlas is unreachable (handles exceptions internally).

        Example:
            >>> chunks = await retriever.retrieve(
            ...     "food spending this month", "user-1", tiers=[2, 3], top_k=8
            ... )
            >>> chunks[0].source_tier
            <MemoryTier.EPISODIC: 2>
        """
        import asyncio

        tiers = tiers or [2, 3, 4, 5]

        # Compute query embedding once
        q_embedding: Optional[List[float]] = None
        if self._embed and 2 in tiers:
            try:
                loop  = asyncio.get_event_loop()
                vec   = await loop.run_in_executor(None, self._embed, query)
                q_embedding = vec.tolist() if hasattr(vec, "tolist") else list(vec)
            except Exception as exc:
                logger.warning(f"[RETRIEVER] Embedding failed: {exc}")

        # Launch parallel pipelines
        tasks = []
        labels = []

        if 2 in tiers:
            if q_embedding:
                tasks.append(self._atlas_vector_retrieve(q_embedding, user_id, k=top_k * 2))
                labels.append("vector")
            tasks.append(self._atlas_text_retrieve(query, user_id, k=top_k * 2))
            labels.append("text")

        if 3 in tiers:
            tasks.append(self._atlas_semantic_retrieve(query, user_id, k=top_k))
            labels.append("semantic")

        if 4 in tiers or 5 in tiers:
            tasks.append(self._atlas_graph_retrieve(query, user_id, k=top_k))
            labels.append("graph")

        if not tasks:
            return []

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect valid results lists
        valid: List[List[RetrievedChunk]] = []
        for label, result in zip(labels, raw_results):
            if isinstance(result, Exception):
                logger.warning(f"[RETRIEVER] Pipeline '{label}' failed: {result}")
                valid.append([])
            else:
                valid.append(result)

        merged = self._rrf_merge(valid, top_k)
        logger.debug(f"[RETRIEVER] {len(merged)} chunks after RRF merge (top_k={top_k})")
        return merged

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE PIPELINES
    # ──────────────────────────────────────────────────────────────────────────

    async def _atlas_vector_retrieve(
        self,
        query_embedding: List[float],
        user_id: str,
        k: int = 20,
    ) -> List[RetrievedChunk]:
        """
        Execute Atlas $vectorSearch aggregation on episodic_memory.

        Returns top-k chunks by cosine similarity.

        Args:
            query_embedding: 384-dim float list.
            user_id: User filter.
            k: Candidates to request from Atlas.

        Returns:
            List of RetrievedChunk from EPISODIC tier.

        Example:
            >>> chunks = await retriever._atlas_vector_retrieve(emb, "user-1", k=15)
        """
        pipeline = [
            {
                "$vectorSearch": {
                    "index"        : _VECTOR_INDEX,
                    "path"         : "embedding",
                    "queryVector"  : query_embedding[:384],
                    "numCandidates": k * 5,
                    "limit"        : k,
                    "filter"       : {
                        "user_id"    : user_id,
                        "decay_score": {"$gte": _MIN_DECAY},
                        "event_type" : {"$ne": "question"},
                    },
                }
            },
            {"$addFields": {"_score": {"$meta": "vectorSearchScore"}}},
            {
                "$project": {
                    "_score"             : 1,
                    "id"                 : 1,
                    "trigger_description": 1,
                    "outcome_description": 1,
                    "event_type"         : 1,
                    "category"           : 1,
                    "amount_inr"         : 1,
                    "decay_score"        : 1,
                }
            },
        ]
        try:
            cursor = self._db["episodic_memory"].aggregate(pipeline)
            docs   = await cursor.to_list(length=k)
            return [_episodic_to_chunk(d, source="vector") for d in docs]
        except Exception as exc:
            logger.warning(f"[RETRIEVER] Vector search failed: {exc}")
            return []

    async def _atlas_text_retrieve(
        self,
        query_text: str,
        user_id: str,
        k: int = 20,
    ) -> List[RetrievedChunk]:
        """
        Execute Atlas $search (BM25) on episodic_memory.

        Args:
            query_text: BM25 query string.
            user_id: User filter.
            k: Number of results.

        Returns:
            List of RetrievedChunk from EPISODIC tier (text-scored).

        Example:
            >>> chunks = await retriever._atlas_text_retrieve("overspend food", "user-1")
        """
        pipeline = [
            {
                "$search": {
                    "index": _TEXT_INDEX_EP,
                    "text" : {
                        "query": query_text,
                        "path" : ["trigger_description", "outcome_description", "category"],
                    },
                }
            },
            {"$match": {
                "user_id": user_id,
                "decay_score": {"$gte": _MIN_DECAY},
                "event_type": {"$ne": "question"}
            }},
            {"$limit": k},
            {"$addFields": {"_score": {"$meta": "searchScore"}}},
            {
                "$project": {
                    "_score"             : 1,
                    "id"                 : 1,
                    "trigger_description": 1,
                    "outcome_description": 1,
                    "event_type"         : 1,
                    "category"           : 1,
                    "amount_inr"         : 1,
                    "decay_score"        : 1,
                }
            },
        ]
        try:
            cursor = self._db["episodic_memory"].aggregate(pipeline)
            docs   = await cursor.to_list(length=k)
            return [_episodic_to_chunk(d, source="text") for d in docs]
        except Exception as exc:
            logger.warning(f"[RETRIEVER] Text search failed: {exc}")
            return []

    async def _atlas_semantic_retrieve(
        self,
        query_text: str,
        user_id: str,
        k: int = 10,
    ) -> List[RetrievedChunk]:
        """
        Execute Atlas $search (BM25) on semantic_memory.

        Args:
            query_text: BM25 query string.
            user_id: User filter.
            k: Number of results.

        Returns:
            List of RetrievedChunk from SEMANTIC tier.

        Example:
            >>> chunks = await retriever._atlas_semantic_retrieve("income monthly", "user-1")
        """
        pipeline = [
            {
                "$search": {
                    "index": _TEXT_INDEX_SM,
                    "text" : {
                        "query": query_text,
                        "path" : ["attribute", "value"],
                    },
                }
            },
            {"$match": {"user_id": user_id}},
            {"$limit": k},
            {"$addFields": {"_score": {"$meta": "searchScore"}}},
        ]
        try:
            cursor = self._db["semantic_memory"].aggregate(pipeline)
            docs   = await cursor.to_list(length=k)
            return [_semantic_to_chunk(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[RETRIEVER] Semantic text search failed: {exc}")
            # Fallback: return top confirmed_count facts
            try:
                cursor = (
                    self._db["semantic_memory"]
                    .find({"user_id": user_id})
                    .sort("confirmed_count", -1)
                    .limit(k)
                )
                docs = await cursor.to_list(length=k)
                return [_semantic_to_chunk(d) for d in docs]
            except Exception:
                return []

    async def _atlas_graph_retrieve(
        self,
        query_text: str,
        user_id: str,
        k: int = 10,
    ) -> List[RetrievedChunk]:
        """
        Execute $graphLookup for multi-hop knowledge graph traversal.

        Extracts entity tokens from query, uses them as startWith nodes.

        Args:
            query_text: Query for entity extraction.
            user_id: Graph owner.
            k: Max path strings to return.

        Returns:
            List of RetrievedChunk from knowledge graph paths.

        Example:
            >>> chunks = await retriever._atlas_graph_retrieve("food overspend goals", "user-1")
        """
        import re
        stops = {"i","my","the","a","is","in","on","to","and","or","of","can","you","when","will","how","what","why"}
        tokens = [t for t in re.findall(r'\b\w+\b', query_text.lower()) if t not in stops and len(t) > 2]
        if not tokens:
            return []

        pipeline = [
            {
                "$match": {
                    "user_id"    : user_id,
                    "source_node": {"$in": tokens},
                }
            },
            {
                "$graphLookup": {
                    "from"                   : "knowledge_graph_edges",
                    "startWith"              : "$target_node",
                    "connectFromField"       : "target_node",
                    "connectToField"         : "source_node",
                    "as"                     : "hops",
                    "maxDepth"               : 2,
                    "restrictSearchWithMatch": {"user_id": user_id},
                }
            },
            {
                "$project": {
                    "source_node" : 1,
                    "relationship": 1,
                    "target_node" : 1,
                    "weight"      : 1,
                    "evidence_count": 1,
                    "hops"        : {"$slice": ["$hops", 5]},
                }
            },
            {"$limit": k},
        ]
        try:
            cursor = self._db["knowledge_graph_edges"].aggregate(pipeline)
            docs   = await cursor.to_list(length=k)
            return [_graph_to_chunk(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[RETRIEVER] Graph lookup failed: {exc}")
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # RRF MERGE (unchanged from original)
    # ──────────────────────────────────────────────────────────────────────────

    def _rrf_merge(
        self,
        result_lists: List[List[RetrievedChunk]],
        top_k: int,
    ) -> List[RetrievedChunk]:
        """
        Reciprocal Rank Fusion merge across multiple result lists.

        Formula: score(d) = sum(1 / (rank_i(d) + k)) for all lists i containing d.

        Args:
            result_lists: Multiple ranked lists of RetrievedChunk.
            top_k: Final number of results.

        Returns:
            Deduplicated, RRF-scored, sorted RetrievedChunk list.

        Example:
            >>> merged = retriever._rrf_merge([vector_results, text_results, graph_results], 10)
        """
        scores: Dict[str, float] = defaultdict(float)
        chunk_map: Dict[str, RetrievedChunk] = {}

        for result_list in result_lists:
            for rank, chunk in enumerate(result_list):
                scores[chunk.chunk_id]    += 1.0 / (rank + _RRF_K)
                chunk_map[chunk.chunk_id]  = chunk

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        merged = []
        for cid, rrf_score in ranked[:top_k]:
            chunk = chunk_map[cid]
            chunk.score = round(rrf_score, 6)
            merged.append(chunk)

        return merged


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _episodic_to_chunk(doc: dict, source: str = "vector") -> RetrievedChunk:
    """Convert episodic_memory Atlas document to RetrievedChunk."""
    content = (
        f"{doc.get('trigger_description', '')} "
        f"{doc.get('outcome_description', '')}"
    ).strip()
    if doc.get("category"):
        content += f" [Category: {doc['category']}]"
    if doc.get("amount_inr"):
        content += f" [Amount: Rs.{doc['amount_inr']:,.0f}]"

    return RetrievedChunk(
        chunk_id    = doc.get("id", str(doc.get("_id", str(uuid.uuid4())))),
        source_tier = MemoryTier.EPISODIC,
        content     = content,
        score       = float(doc.get("_score", 0.5)),
        metadata    = {
            "event_type"  : doc.get("event_type"),
            "decay_score" : doc.get("decay_score", 1.0),
            "source_method": source,
        },
    )


def _semantic_to_chunk(doc: dict) -> RetrievedChunk:
    """Convert semantic_memory Atlas document to RetrievedChunk."""
    content = f"{doc.get('attribute', '')}: {doc.get('value', '')}"
    return RetrievedChunk(
        chunk_id    = doc.get("id", str(doc.get("_id", str(uuid.uuid4())))),
        source_tier = MemoryTier.SEMANTIC,
        content     = content,
        score       = float(doc.get("_score", doc.get("confidence_score", 0.5))),
        metadata    = {
            "memory_type"   : doc.get("memory_type"),
            "confirmed_count": doc.get("confirmed_count", 0),
            "source_method" : "bm25",
        },
    )


def _graph_to_chunk(doc: dict) -> RetrievedChunk:
    """Convert knowledge_graph_edge Atlas document (with hops) to RetrievedChunk."""
    w   = doc.get("weight", 1.0)
    n   = doc.get("evidence_count", 1)
    path = f"{doc.get('source_node')} → {doc.get('relationship')} → {doc.get('target_node')} (w={w:.1f}, n={n})"

    hops = doc.get("hops", [])
    if hops:
        hop_strs = [
            f"{h.get('source_node')} → {h.get('relationship')} → {h.get('target_node')}"
            for h in hops[:3]
        ]
        path += " | " + " → ".join(hop_strs)

    return RetrievedChunk(
        chunk_id    = str(doc.get("_id", str(uuid.uuid4()))),
        source_tier = MemoryTier.SEMANTIC,   # closest tier for graph
        content     = path,
        score       = min(1.0, float(w) / 10.0),
        metadata    = {
            "source_method": "graph",
            "weight"       : w,
            "evidence_count": n,
        },
    )
