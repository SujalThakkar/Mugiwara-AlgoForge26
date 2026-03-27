"""
rag/query_router.py — Adaptive intent classification and retrieval routing.

Two-stage classification:
  1. Keyword pattern matching (O(1), zero latency)
  2. Embedding similarity fallback for ambiguous queries (single vector op)

No additional LLM call — uses only lightweight heuristics + embeddings.

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

from models.schemas import QueryIntent, RouteDecision

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTING TABLE
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_PATTERNS: Dict[QueryIntent, List[str]] = {
    QueryIntent.SIMPLE_LOOKUP: [
        "what did i spend", "how much did i", "show me", "list my",
        "how many transactions", "last transaction", "recent spend",
        "what was", "tell me about", "details of",
    ],
    QueryIntent.TREND_ANALYSIS: [
        "am i spending more", "trend", "pattern", "compared to last",
        "month over month", "week over week", "increasing", "decreasing",
        "vs last", "change in", "historically",
    ],
    QueryIntent.GOAL_PLANNING: [
        "how do i save", "can i afford", "when will i reach", "goal",
        "target", "plan to", "saving for", "how long until", "timeline",
        "milestone", "emergency fund",
    ],
    QueryIntent.SCENARIO_SIM: [
        "what if", "if i cut", "if i reduce", "suppose i", "hypothetically",
        "if my salary", "if i stop", "what happens if", "simulate",
        "what would", "scenario",
    ],
    QueryIntent.BEHAVIORAL: [
        "why do i", "help me stop", "i always", "my habit", "i keep",
        "why am i", "i can't stop", "impulse", "overspend",
        "discipline", "self control",
    ],
    QueryIntent.FULL_ADVISORY: [
        "am i doing well", "financial health", "overall advice",
        "financial review", "how am i doing", "assess my", "audit my",
        "full picture", "everything", "general advice", "what should i",
    ],
}

_ROUTE_CONFIGS: Dict[QueryIntent, Dict] = {
    QueryIntent.SIMPLE_LOOKUP  : {"use_llm": False, "db_direct": True,  "tiers": [1],          "use_simulation": False},
    QueryIntent.TREND_ANALYSIS : {"use_llm": True,  "db_direct": False, "tiers": [2, 3],        "use_simulation": False},
    QueryIntent.GOAL_PLANNING  : {"use_llm": True,  "db_direct": False, "tiers": [3, 4, 5],     "use_simulation": True },
    QueryIntent.SCENARIO_SIM   : {"use_llm": True,  "db_direct": False, "tiers": [4, 3, 5],     "use_simulation": True },
    QueryIntent.BEHAVIORAL     : {"use_llm": True,  "db_direct": False, "tiers": [5, 2, 3],     "use_simulation": False},
    QueryIntent.FULL_ADVISORY  : {"use_llm": True,  "db_direct": False, "tiers": [1, 2, 3, 4, 5], "use_simulation": True},
}

# Canonical query embeddings for each intent (used in similarity fallback)
_INTENT_SEEDS: Dict[QueryIntent, str] = {
    QueryIntent.SIMPLE_LOOKUP  : "show me what I spent on food last week",
    QueryIntent.TREND_ANALYSIS : "am I spending more this month compared to last?",
    QueryIntent.GOAL_PLANNING  : "how many months until I reach my emergency fund goal?",
    QueryIntent.SCENARIO_SIM   : "what if I cut dining expenses by 30 percent?",
    QueryIntent.BEHAVIORAL     : "why do I always overspend on weekends?",
    QueryIntent.FULL_ADVISORY  : "give me a full review of my financial health",
}


class QueryRouter:
    """
    Adaptive query intent classifier and retrieval router.

    Uses keyword matching first (zero cost). Falls back to embedding
    similarity only when no strong keyword match is found.

    Usage:
        router = QueryRouter(embedding_fn=my_embed_fn)
        decision = await router.route("what if I stopped eating out?", "user-1")

    Attributes:
        _embed: Optional async-compatible embedding function.
        _seed_vecs: Precomputed embeddings for each intent seed (lazy init).
    """

    def __init__(self, embedding_fn: Optional[Callable] = None):
        self._embed     = embedding_fn
        self._seed_vecs: Optional[Dict[QueryIntent, "np.ndarray"]] = None

    async def route(self, query: str, user_id: str) -> RouteDecision:
        """
        Classify query intent and return a RouteDecision.

        Strategy:
          1. Score each intent by keyword overlap (count of matching phrases).
          2. If top score ≥ 2 → strong keyword match → use that intent.
          3. If tie or score == 1 → use embedding similarity to break tie.
          4. If no match → default to FULL_ADVISORY.

        Args:
            query: Natural language user query.
            user_id: Not used for routing, included for audit purposes.

        Returns:
            RouteDecision with intent, tiers, and simulation flag.

        Example:
            >>> decision = await router.route("what if I invest ₹5,000 more monthly?", "u1")
            >>> decision.intent
            <QueryIntent.SCENARIO_SIM: 'SCENARIO_SIM'>
        """
        q_lower = query.lower()

        # Step 1: Keyword scoring
        keyword_scores: Dict[QueryIntent, Tuple[int, List[str]]] = {}
        for intent, patterns in _INTENT_PATTERNS.items():
            matches = [p for p in patterns if p in q_lower]
            keyword_scores[intent] = (len(matches), matches)

        top_intent = max(keyword_scores, key=lambda k: keyword_scores[k][0])
        top_score, top_matches = keyword_scores[top_intent]

        # Step 2: Strong match
        if top_score >= 2:
            return self._build_decision(top_intent, top_matches, confidence=0.95)

        # Step 3: Weak match — try embedding similarity
        if top_score == 1 and self._embed:
            try:
                intent_from_emb, sim = await self._embed_classify(query)
                if sim > 0.75:
                    return self._build_decision(intent_from_emb, [], confidence=sim)
            except Exception as e:
                logger.debug(f"[ROUTER] Embedding fallback failed: {e}")

        if top_score == 1:
            return self._build_decision(top_intent, top_matches, confidence=0.65)

        # Step 4: Default
        logger.debug(f"[ROUTER] No match for '{query[:50]}' → FULL_ADVISORY")
        return self._build_decision(QueryIntent.FULL_ADVISORY, [], confidence=0.40)

    def _build_decision(
        self,
        intent: QueryIntent,
        matched_keywords: List[str],
        confidence: float,
    ) -> RouteDecision:
        cfg = _ROUTE_CONFIGS[intent]
        decision = RouteDecision(
            intent           = intent,
            tiers_to_query   = cfg["tiers"],
            use_simulation   = cfg["use_simulation"],
            use_llm          = cfg["use_llm"],
            db_direct        = cfg["db_direct"],
            confidence       = confidence,
            matched_keywords = matched_keywords,
        )
        logger.info(
            f"[ROUTER] intent={intent.value} conf={confidence:.2f} "
            f"keywords={matched_keywords[:3]}"
        )
        return decision

    async def _embed_classify(self, query: str) -> Tuple[QueryIntent, float]:
        """
        Compute cosine similarity of query vs seed embeddings.
        Returns the best (intent, similarity_score).
        """
        import numpy as np

        if self._seed_vecs is None:
            await self._precompute_seeds()

        loop   = asyncio.get_event_loop()
        q_vec  = await loop.run_in_executor(None, self._embed, query)
        q_arr  = np.array(q_vec, dtype=np.float32)
        q_norm = np.linalg.norm(q_arr)

        best_intent = QueryIntent.FULL_ADVISORY
        best_sim    = 0.0

        for intent, seed_vec in self._seed_vecs.items():
            dot  = float(np.dot(q_arr, seed_vec))
            denom= q_norm * np.linalg.norm(seed_vec)
            sim  = dot / denom if denom > 1e-9 else 0.0
            if sim > best_sim:
                best_sim    = sim
                best_intent = intent

        return best_intent, best_sim

    async def _precompute_seeds(self) -> None:
        """Lazy initialise seed embeddings for each intent."""
        import numpy as np

        loop = asyncio.get_event_loop()
        self._seed_vecs = {}
        for intent, seed_text in _INTENT_SEEDS.items():
            try:
                vec = await loop.run_in_executor(None, self._embed, seed_text)
                self._seed_vecs[intent] = np.array(vec, dtype=np.float32)
            except Exception as e:
                logger.warning(f"[ROUTER] Seed embed failed for {intent}: {e}")
