"""
memory/knowledge_graph.py — Tier 3b: Relationship graph on Atlas via $graphLookup.

Replaces NetworkX in-memory graph with Atlas aggregation.
Edges stored in MongoDB collection 'knowledge_graph_edges'.

Multi-hop traversal implemented via $graphLookup (maxDepth=2, M0-safe).
All queries restricted to single user_id for performance.

Collection: knowledge_graph_edges
Indexes:
  {user_id:1, source_node:1, relationship:1}
  {user_id:1, target_node:1}
  {user_id:1, source_node:1, target_node:1} — unique

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from models.schemas import EdgeRelationship, KnowledgeGraphEdge

logger = logging.getLogger(__name__)

_COLLECTION = "knowledge_graph_edges"


class KnowledgeGraphStore:
    """
    Atlas-backed Tier 3b knowledge graph.

    Usage:
        store = KnowledgeGraphStore(db)
        await store.upsert_edge("user-1", "user", "OVERSPENDS_ON", "food", "category")
        paths = await store.multi_hop_query("user-1", ["food", "dining"])
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[_COLLECTION]

    # ──────────────────────────────────────────────────────────────────────────
    # WRITES
    # ──────────────────────────────────────────────────────────────────────────

    async def upsert_edge(
        self,
        user_id: str,
        source_node: str,
        relationship: EdgeRelationship,
        target_node: str,
        source_type: str = "unknown",
        target_type: str = "unknown",
        weight_delta: float = 1.0,
    ) -> None:
        """
        Insert or strengthen a knowledge graph edge.

        If edge exists: weight += weight_delta, evidence_count += 1.
        If new: insert with weight=1.0, evidence_count=1.

        Args:
            user_id: User that owns this edge.
            source_node: Source entity string (e.g., "food", "Zomato").
            relationship: EdgeRelationship enum.
            target_node: Target entity string.
            source_type: Type label for source (e.g., "category", "merchant").
            target_type: Type label for target.
            weight_delta: Amount to increase edge weight.

        Example:
            >>> await store.upsert_edge(
            ...     "user-1", "user", EdgeRelationship.OVERSPENDS_ON,
            ...     "food", "entity", "category", weight_delta=1.5
            ... )
        """
        try:
            await self._col.update_one(
                {
                    "user_id"     : user_id,
                    "source_node" : source_node,
                    "relationship": relationship.value,
                    "target_node" : target_node,
                },
                {
                    "$inc": {"weight": weight_delta, "evidence_count": 1},
                    "$set": {"last_updated": datetime.utcnow()},
                    "$setOnInsert": {
                        "id"          : str(uuid.uuid4()),
                        "user_id"     : user_id,
                        "source_node" : source_node,
                        "source_type" : source_type,
                        "relationship": relationship.value,
                        "target_node" : target_node,
                        "target_type" : target_type,
                    },
                },
                upsert=True,
            )
        except Exception as exc:
            logger.warning(f"[KG] Edge upsert failed: {exc}")

    async def bulk_upsert_edges(
        self, user_id: str, edges: List[Dict]
    ) -> int:
        """
        Upsert multiple edges via bulk_write.

        Args:
            user_id: User owner.
            edges: List of dicts with keys: source_node, relationship, target_node,
                   source_type, target_type, weight_delta.

        Returns:
            Number of edges affected.

        Example:
            >>> n = await store.bulk_upsert_edges("user-1", [
            ...     {"source_node": "user", "relationship": "OVERSPENDS_ON",
            ...      "target_node": "food", "source_type": "entity",
            ...      "target_type": "category", "weight_delta": 1.0}
            ... ])
        """
        if not edges:
            return 0
        ops = []
        for e in edges:
            ops.append(UpdateOne(
                {
                    "user_id"     : user_id,
                    "source_node" : e["source_node"],
                    "relationship": e.get("relationship", "RELATED_TO"),
                    "target_node" : e["target_node"],
                },
                {
                    "$inc": {"weight": e.get("weight_delta", 1.0), "evidence_count": 1},
                    "$set": {"last_updated": datetime.utcnow()},
                    "$setOnInsert": {
                        "id"          : str(uuid.uuid4()),
                        "user_id"     : user_id,
                        "source_node" : e["source_node"],
                        "source_type" : e.get("source_type", "unknown"),
                        "relationship": e.get("relationship", "RELATED_TO"),
                        "target_node" : e["target_node"],
                        "target_type" : e.get("target_type", "unknown"),
                    },
                },
                upsert=True,
            ))
        try:
            res = await self._col.bulk_write(ops, ordered=False)
            return res.upserted_count + res.modified_count
        except Exception as exc:
            logger.warning(f"[KG] Bulk edge upsert failed: {exc}")
            return 0

    # ──────────────────────────────────────────────────────────────────────────
    # READS — $graphLookup
    # ──────────────────────────────────────────────────────────────────────────

    async def multi_hop_query(
        self,
        user_id: str,
        start_nodes: List[str],
        max_depth: int = 2,
    ) -> List[str]:
        """
        Traverse the knowledge graph up to max_depth hops using $graphLookup.

        Restricted to single user_id for M0 performance.
        Returns human-readable path strings for prompt injection.

        Args:
            user_id: Owner user — all traversal stays within this user's graph.
            start_nodes: Entity names to start traversal from.
            max_depth: Maximum hop depth (2 = default, M0-safe).

        Returns:
            List of path strings like "food → OVERSPENDS_ON → Zomato (w=3.5)".

        Example:
            >>> paths = await store.multi_hop_query("user-1", ["food", "dining"])
            >>> paths[0]
            'food → OVERSPENDS_ON → Zomato (w=2.0, n=4)'
        """
        if not start_nodes:
            return []

        pipeline = [
            {
                "$match": {
                    "user_id"    : user_id,
                    "source_node": {"$in": start_nodes},
                }
            },
            {
                "$graphLookup": {
                    "from"                   : _COLLECTION,
                    "startWith"              : "$target_node",
                    "connectFromField"       : "target_node",
                    "connectToField"         : "source_node",
                    "as"                     : "graph_path",
                    "maxDepth"               : max_depth,
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
                    "graph_path"  : {
                        "$slice": ["$graph_path", 10]  # cap per root to avoid blowup
                    },
                }
            },
            {"$limit": 20},   # M0 safeguard
        ]

        try:
            cursor = self._col.aggregate(pipeline)
            docs   = await cursor.to_list(length=50)
        except Exception as exc:
            logger.warning(f"[KG] $graphLookup failed: {exc}")
            return []

        path_strings: List[str] = []
        seen: set = set()

        for doc in docs:
            path = _edge_to_str(doc)
            if path not in seen:
                path_strings.append(path)
                seen.add(path)

            for hop in doc.get("graph_path", []):
                hop_path = _edge_to_str(hop)
                if hop_path not in seen:
                    path_strings.append(hop_path)
                    seen.add(hop_path)

        return path_strings[:20]

    async def get_spending_patterns(
        self, user_id: str, limit: int = 10
    ) -> List[KnowledgeGraphEdge]:
        """
        Return OVERSPENDS_ON edges sorted by weight DESC.

        Args:
            user_id: User identifier.
            limit: Max edges to return.

        Returns:
            Highest-weight overspend relationships.

        Example:
            >>> patterns = await store.get_spending_patterns("user-1")
            >>> patterns[0].target_node
            'food'
        """
        try:
            cursor = (
                self._col.find(
                    {"user_id": user_id, "relationship": EdgeRelationship.OVERSPENDS_ON.value}
                )
                .sort("weight", -1)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return [_doc_to_edge(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[KG] Spending patterns failed: {exc}")
            return []

    async def get_competing_goals(
        self, user_id: str, category: str
    ) -> List[KnowledgeGraphEdge]:
        """
        Find goals that COMPETES_WITH the given spending category.

        Args:
            user_id: User identifier.
            category: Spending category to check competition for.

        Returns:
            List of competing goal edges.

        Example:
            >>> goals = await store.get_competing_goals("user-1", "dining")
        """
        try:
            cursor = self._col.find({
                "user_id"     : user_id,
                "relationship": EdgeRelationship.COMPETES_WITH.value,
                "$or"         : [
                    {"source_node": category},
                    {"target_node": category},
                ],
            })
            docs = await cursor.to_list(length=10)
            return [_doc_to_edge(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[KG] Competing goals failed: {exc}")
            return []

    async def bootstrap_for_new_user(self, user_id: str) -> None:
        """
        Seed default graph edges for a new user with zero transaction history.

        Creates neutral starting edges that the system can strengthen over time.

        Args:
            user_id: New user to bootstrap.

        Example:
            >>> await store.bootstrap_for_new_user("new-user-123")
        """
        default_edges = [
            ("user", EdgeRelationship.TARGETS,    "savings",     "entity", "goal"),
            ("user", EdgeRelationship.TARGETS,    "emergency_fund", "entity", "goal"),
            ("food", EdgeRelationship.COMPETES_WITH, "savings",  "category", "goal"),
            ("shopping", EdgeRelationship.COMPETES_WITH, "savings", "category", "goal"),
        ]
        for src, rel, tgt, st, tt in default_edges:
            try:
                await self._col.update_one(
                    {"user_id": user_id, "source_node": src, "relationship": rel.value, "target_node": tgt},
                    {
                        "$setOnInsert": {
                            "id"           : str(uuid.uuid4()),
                            "user_id"      : user_id,
                            "source_node"  : src,
                            "source_type"  : st,
                            "relationship" : rel.value,
                            "target_node"  : tgt,
                            "target_type"  : tt,
                            "weight"       : 0.5,
                            "evidence_count": 0,
                            "last_updated" : datetime.utcnow(),
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass

    async def retrieve(
        self,
        user_id: str,
        query: str = "",
        limit: int = 10,
        query_embedding: Optional[object] = None,
    ) -> List[str]:
        """
        Backward-compatible retrieve interface — returns graph paths.
        Extracts entity tokens from query text as start_nodes.

        Args:
            user_id: User identifier.
            query: Query string for entity extraction.
            limit: Max paths to return.
            query_embedding: Ignored (interface compatibility).

        Returns:
            List of graph path strings.
        """
        import re
        stops = {"i", "my", "the", "a", "is", "in", "on", "to", "and", "or", "of", "can", "you", "when", "will"}
        tokens = [t for t in re.findall(r'\b\w+\b', query.lower()) if t not in stops and len(t) > 2]
        return await self.multi_hop_query(user_id, tokens[:5], max_depth=2)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _edge_to_str(doc: dict) -> str:
    """Format an edge document as a readable path string."""
    w  = doc.get("weight", 1.0)
    n  = doc.get("evidence_count", 1)
    return f"{doc.get('source_node')} → {doc.get('relationship')} → {doc.get('target_node')} (w={w:.1f}, n={n})"


def _doc_to_edge(doc: dict) -> KnowledgeGraphEdge:
    """Convert Atlas document to KnowledgeGraphEdge model."""
    try:
        rel = EdgeRelationship(doc.get("relationship", "RELATED_TO"))
    except ValueError:
        rel = EdgeRelationship.OVERSPENDS_ON
    return KnowledgeGraphEdge(
        id             = doc.get("id", str(doc.get("_id", ""))),
        user_id        = doc["user_id"],
        source_node    = doc.get("source_node", ""),
        source_type    = doc.get("source_type", "unknown"),
        relationship   = rel,
        target_node    = doc.get("target_node", ""),
        target_type    = doc.get("target_type", "unknown"),
        weight         = float(doc.get("weight", 1.0)),
        evidence_count = int(doc.get("evidence_count", 1)),
        last_updated   = doc.get("last_updated", datetime.utcnow()),
    )
