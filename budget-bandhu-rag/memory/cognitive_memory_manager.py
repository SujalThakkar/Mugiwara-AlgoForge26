"""
memory/cognitive_memory_manager.py — Unified 5-tier memory orchestrator.

Routes operations to the correct store:
  Tier 1 (Working)   → SQLite (always local)
  Tiers 2-5          → MongoDB Atlas (with fallback to SQLite mirrors)

On Atlas timeout: switch_to_fallback() activates automatically.
On Atlas recovery: switch_to_atlas() drains write buffer.

Public interface is IDENTICAL to the old SQLite-only implementation.

Author: Financial Cognitive OS Team
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from database.fallback_bridge import AtlasFallbackBridge
from memory.episodic_memory import EpisodicMemoryStore
from memory.knowledge_graph import KnowledgeGraphStore
from memory.procedural_memory import ProceduralMemoryStore
from memory.semantic_memory import SemanticMemoryStore
from memory.trajectory_memory import TrajectoryMemoryStore
from memory.working_memory import WorkingMemoryStore
from models.schemas import (
    BehavioralArchetype, EpisodicMemory, ProceduralMemory,
    QueryIntent, SemanticMemory, TrajectoryMemory, UnifiedMemoryContext,
)

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = 2048
_ATLAS_TIMEOUT_S      = 5.0   # seconds before giving up on a single Atlas call


class CognitiveMemoryManager:
    """
    Unified 5-tier cognitive memory orchestrator.

    Wires together:
      working    → SQLite (aiosqlite)
      episodic   → Atlas EpisodicMemoryStore
      semantic   → Atlas SemanticMemoryStore
      graph      → Atlas KnowledgeGraphStore
      procedural → Atlas ProceduralMemoryStore
      trajectory → Atlas TrajectoryMemoryStore
      fallback   → AtlasFallbackBridge (SQLite mirrors on timeout)

    Usage:
        mgr = CognitiveMemoryManager(sqlite_path, atlas_db, embedding_fn)
        await mgr.start()
        ctx = await mgr.get_unified_context(user_id, query, intent, session_id)
    """

    def __init__(
        self,
        sqlite_path: str,
        atlas_db: AsyncIOMotorDatabase,
        embedding_fn: Optional[Callable] = None,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
    ):
        self._sqlite_path  = sqlite_path
        self._atlas_db     = atlas_db
        self._embed        = embedding_fn
        self._token_budget = token_budget

        # Tier 1 — SQLite store
        self.working     = WorkingMemoryStore(sqlite_path)

        # Tiers 2-5 — Atlas stores
        self.episodic    = EpisodicMemoryStore(atlas_db, embedding_fn)
        self.semantic    = SemanticMemoryStore(atlas_db, embedding_fn)
        self.graph       = KnowledgeGraphStore(atlas_db)
        self.procedural  = ProceduralMemoryStore(atlas_db)
        self.trajectory  = TrajectoryMemoryStore(atlas_db)

        # Failover
        self.fallback    = AtlasFallbackBridge(sqlite_path)

    async def start(self) -> None:
        """Start background processes (fallback recovery loop)."""
        await self.fallback.start()

    async def stop(self) -> None:
        """Graceful shutdown."""
        await self.fallback.stop()

    # ──────────────────────────────────────────────────────────────────────────
    # UNIFIED CONTEXT FETCH (PRIMARY ENTRY POINT)
    # ──────────────────────────────────────────────────────────────────────────

    async def get_unified_context(
        self,
        user_id: str,
        query: str,
        query_intent: QueryIntent,
        session_id: str,
    ) -> UnifiedMemoryContext:
        """
        Fetch memory from all relevant tiers in parallel.

        Tiers activated by intent:
          SIMPLE_LOOKUP  → Working + Episodic (text) + Semantic
          TREND_ANALYSIS → Working + Episodic (hybrid) + Trajectory
          GOAL_PLANNING  → Working + Semantic + Procedural + Trajectory
          SCENARIO_SIM   → Working + Episodic (hybrid) + Procedural
          BEHAVIORAL     → All 5 tiers
          FULL_ADVISORY  → All 5 tiers

        Args:
            user_id: User identifier.
            query: User's query text.
            query_intent: Classified query intent.
            session_id: Current session ID.

        Returns:
            UnifiedMemoryContext with all available tier data.

        Example:
            >>> ctx = await mgr.get_unified_context(
            ...     "user-1", "Why am I overspending on food?",
            ...     QueryIntent.TREND_ANALYSIS, "session-abc"
            ... )
        """
        t0 = datetime.utcnow()

        # Compute query embedding (if available)
        q_embedding: Optional[List[float]] = None
        if self._embed:
            try:
                vec         = await asyncio.get_event_loop().run_in_executor(
                    None, self._embed, query
                )
                q_embedding = vec.tolist() if hasattr(vec, "tolist") else list(vec)
            except Exception:
                pass

        # Determine which tiers to activate
        active_tiers = _get_active_tiers(query_intent)

        # Build parallel fetch tasks
        tasks: Dict[str, asyncio.Task] = {}

        # Tier 1 — always
        tasks["working"] = asyncio.ensure_future(
            self._safe(self.working.get_session_items(session_id, user_id, limit=10), [])
        )

        if "episodic" in active_tiers:
            tasks["episodic"] = asyncio.ensure_future(
                self._safe_atlas(
                    self.episodic.hybrid_search(q_embedding, query, user_id, k=8),
                    self.fallback.fallback_episodic_read(user_id, limit=8, query_text=query),
                )
            )

        if "semantic" in active_tiers:
            tasks["semantic"] = asyncio.ensure_future(
                self._safe_atlas(
                    self.semantic.get_profile(user_id, limit=15),
                    self.fallback.fallback_semantic_read(user_id, limit=15),
                )
            )

        if "graph" in active_tiers:
            tasks["graph"] = asyncio.ensure_future(
                self._safe_atlas(
                    self.graph.retrieve(user_id, query=query, limit=10),
                    [],
                )
            )

        if "procedural" in active_tiers:
            tasks["procedural"] = asyncio.ensure_future(
                self._safe_atlas(
                    self.procedural.get_best_strategy(user_id, _intent_to_event(query_intent)),
                    None,
                )
            )

        if "trajectory" in active_tiers:
            tasks["trajectory"] = asyncio.ensure_future(
                self._safe_atlas(
                    self.trajectory.get_latest_snapshot(user_id),
                    None,
                )
            )

        # Await all
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result_map = dict(zip(tasks.keys(), results))

        # Unpack
        def _r(key, default):
            v = result_map.get(key, default)
            return default if isinstance(v, Exception) else v

        working_items   = _r("working",    [])
        episodic_list   = _r("episodic",   [])
        semantic_list   = _r("semantic",   [])
        graph_paths     = _r("graph",      [])
        procedural      = _r("procedural", None)
        traj            = _r("trajectory", None)

        # Convert fallback dicts to model instances if needed
        episodic_list = _coerce_episodic(episodic_list)
        semantic_list = _coerce_semantic(semantic_list)

        tiers_loaded = ["WORKING"] + [t.upper() for t in active_tiers]

        elapsed = (datetime.utcnow() - t0).total_seconds() * 1000

        return UnifiedMemoryContext(
            user_id                = user_id,
            session_id             = session_id,
            query_intent           = query_intent,
            working                = working_items,
            episodic               = episodic_list,
            semantic               = semantic_list,
            graph_paths            = graph_paths if isinstance(graph_paths, list) else [],
            procedural             = procedural if isinstance(procedural, ProceduralMemory) else None,
            trajectory             = traj if isinstance(traj, TrajectoryMemory) else None,
            total_tokens_estimated = _estimate_tokens(episodic_list, semantic_list, graph_paths),
            tiers_loaded           = tiers_loaded,
            retrieval_time_ms      = round(elapsed, 1),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # WRITE HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    async def write_episodic(
        self,
        user_id: str,
        event_type: str,
        trigger: str,
        outcome: str,
        session_id: Optional[str] = None,
        category: Optional[str] = None,
        amount_inr: Optional[float] = None,
    ) -> str:
        """
        Write an episodic memory to Atlas, with SQLite fallback buffer on failure.

        Args:
            user_id: User identifier.
            event_type: Event class (OVERSPEND, SUCCESS, etc.).
            trigger: What happened.
            outcome: Response / outcome.
            session_id: Session ID.
            category: Spending category.
            amount_inr: Amount in Rupees.

        Returns:
            Episode ID string.

        Example:
            >>> eid = await mgr.write_episodic(
            ...     "user-1", "OVERSPEND", "Spent Rs.3000 on Zomato",
            ...     "Advised to set cap", category="food"
            ... )
        """
        try:
            ep_id = await asyncio.wait_for(
                self.episodic.store_episode(
                    user_id        = user_id,
                    event_type     = event_type,
                    trigger_description = trigger,
                    outcome_description = outcome,
                    session_id     = session_id,
                    category       = category,
                    amount_inr     = amount_inr,
                ),
                timeout=_ATLAS_TIMEOUT_S,
            )
            return ep_id
        except asyncio.TimeoutError:
            await self.fallback.switch_to_fallback("Atlas write timeout (episodic)")
            fallback_record = {
                "id"                 : str(uuid.uuid4()),
                "user_id"            : user_id,
                "event_type"         : event_type,
                "trigger_description": trigger,
                "outcome_description": outcome,
                "category"           : category,
                "amount_inr"         : amount_inr,
                "decay_score"        : 1.0,
                "confidence_score"   : 0.5,
                "created_at"         : datetime.utcnow().isoformat(),
            }
            await self.fallback.fallback_write_episodic(fallback_record)
            self.fallback.buffer_write("episodic_memory", "insert", fallback_record)
            return fallback_record["id"]
        except Exception as exc:
            logger.error(f"[CMM] write_episodic failed: {exc}")
            return ""

    async def flush_working_to_episodic(
        self, session_id: str, user_id: str
    ) -> None:
        """
        Archive important working memory items to episodic memory at session end.

        Items with importance_score > 0.7 are promoted.
        All working memory items for this session are cleared.

        Args:
            session_id: Session to flush.
            user_id: User identifier.

        Example:
            >>> await mgr.flush_working_to_episodic(session_id, user_id)
        """
        try:
            candidates = await self.working.get_flush_candidates(session_id, user_id, min_importance=0.7)
            for item in candidates:
                content = item.content_json
                asyncio.create_task(
                    self.write_episodic(
                        user_id    = user_id,
                        event_type = "SESSION_CONTEXT",
                        trigger    = str(content.get("text", ""))[:500],
                        outcome    = f"Type: {item.content_type}",
                        session_id = session_id,
                    )
                )
            await self.working.clear_session(session_id, user_id)
        except Exception as exc:
            logger.warning(f"[CMM] Flush working failed: {exc}")

    async def bootstrap_new_user(self, user_id: str) -> None:
        """
        Bootstrap a brand-new user with default strategies and KG edges.

        Called when a user has zero Atlas data (cold start).

        Args:
            user_id: New user to bootstrap.

        Example:
            >>> await mgr.bootstrap_new_user("brand-new-user")
        """
        await asyncio.gather(
            self.procedural.seed_default_strategies(user_id),
            self.graph.bootstrap_for_new_user(user_id),
            return_exceptions=True,
        )
        logger.info(f"[CMM] Bootstrap complete for new user: {user_id}")

    # ──────────────────────────────────────────────────────────────────────────
    # SAFE WRAPPERS
    # ──────────────────────────────────────────────────────────────────────────

    async def _safe(self, coro, default):
        """Execute coroutine, return default on any exception."""
        try:
            return await coro
        except Exception as exc:
            logger.debug(f"[CMM] Safe call failed: {exc}")
            return default

    async def _safe_atlas(self, atlas_coro, fallback_coro):
        """
        Execute Atlas coroutine with timeout.
        On timeout or error: activate fallback, execute fallback_coro.

        Args:
            atlas_coro: Atlas Motor coroutine.
            fallback_coro: Fallback coroutine (SQLite or empty).

        Returns:
            Result of atlas_coro on success, result of fallback_coro on failure.
        """
        try:
            return await asyncio.wait_for(atlas_coro, timeout=_ATLAS_TIMEOUT_S)
        except asyncio.TimeoutError:
            await self.fallback.switch_to_fallback("Atlas timeout in memory fetch")
            try:
                return await fallback_coro
            except Exception:
                return [] if isinstance(fallback_coro, list) else None
        except Exception as exc:
            logger.warning(f"[CMM] Atlas fetch failed: {exc}")
            try:
                return await fallback_coro
            except Exception:
                return [] if isinstance(fallback_coro, list) else None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_tiers(intent: QueryIntent) -> List[str]:
    """Map intent to tier set."""
    tier_map = {
        QueryIntent.SIMPLE_LOOKUP : ["episodic", "semantic"],
        QueryIntent.TREND_ANALYSIS: ["episodic", "trajectory"],
        QueryIntent.GOAL_PLANNING : ["semantic", "procedural", "trajectory"],
        QueryIntent.SCENARIO_SIM  : ["episodic", "procedural"],
        QueryIntent.BEHAVIORAL    : ["episodic", "semantic", "graph", "procedural", "trajectory"],
        QueryIntent.FULL_ADVISORY : ["episodic", "semantic", "graph", "procedural", "trajectory"],
    }
    return tier_map.get(intent, ["episodic", "semantic"])


def _intent_to_event(intent: QueryIntent) -> str:
    """Map query intent to closest procedural event_type."""
    mapping = {
        QueryIntent.SIMPLE_LOOKUP : "SIMPLE_QUERY",
        QueryIntent.TREND_ANALYSIS: "TREND_QUERY",
        QueryIntent.GOAL_PLANNING : "SAVINGS_MILESTONE",
        QueryIntent.SCENARIO_SIM  : "SCENARIO_QUERY",
        QueryIntent.BEHAVIORAL    : "OVERSPEND",
        QueryIntent.FULL_ADVISORY : "OVERSPEND",
    }
    return mapping.get(intent, "OVERSPEND")


def _estimate_tokens(episodic: list, semantic: list, graph: list) -> int:
    """Rough token count estimate for context budget tracking."""
    CHARS_PER_TOKEN = 4
    total_chars = 0
    for ep in episodic:
        total_chars += len(getattr(ep, "trigger_description", str(ep)))
    for sm in semantic:
        total_chars += len(f"{getattr(sm, 'attribute', '')} {getattr(sm, 'value', '')}")
    for gp in graph:
        total_chars += len(str(gp))
    return total_chars // CHARS_PER_TOKEN


def _coerce_episodic(items: list) -> List[EpisodicMemory]:
    """Convert fallback dicts to EpisodicMemory if needed."""
    from models.schemas import UserReaction
    result = []
    for item in items:
        if isinstance(item, EpisodicMemory):
            result.append(item)
        elif isinstance(item, dict):
            try:
                result.append(EpisodicMemory(
                    id                  = item.get("id", str(uuid.uuid4())),
                    user_id             = item.get("user_id", ""),
                    event_type          = item.get("event_type", "UNKNOWN"),
                    trigger_description = item.get("trigger_description", ""),
                    outcome_description = item.get("outcome_description", ""),
                    decay_score         = float(item.get("decay_score", 1.0)),
                    confidence_score    = float(item.get("confidence_score", 0.5)),
                ))
            except Exception:
                pass
    return result


def _coerce_semantic(items: list) -> List[SemanticMemory]:
    """Convert fallback dicts to SemanticMemory if needed."""
    result = []
    for item in items:
        if isinstance(item, SemanticMemory):
            result.append(item)
        elif isinstance(item, dict):
            try:
                result.append(SemanticMemory(
                    id               = item.get("id", str(uuid.uuid4())),
                    user_id          = item.get("user_id", ""),
                    memory_type      = item.get("memory_type", "UNKNOWN"),
                    attribute        = item.get("attribute", ""),
                    value            = item.get("value", ""),
                    confidence_score = float(item.get("confidence_score", 0.5)),
                    confirmed_count  = int(item.get("confirmed_count", 0)),
                ))
            except Exception:
                pass
    return result
