"""
rag/reranker.py — Heuristic cross-encoder reranker for final result set.

No external model needed. Re-scores chunks using:
  1. Financial entity density (₹ amounts, categories, dates)
  2. Query-specific keyword presence
  3. Recency bonus (episodic memories from last 7 days get +0.1)
  4. Source tier diversity bonus (avoid mono-source bias)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

from models.schemas import GradedChunk, MemoryTier, RetrievedChunk

logger = logging.getLogger(__name__)

_AMOUNT_RE   = re.compile(r'Rs\.?\s*[\d,]+|₹[\d,]+|\d{1,3}(?:,\d{3})+', re.IGNORECASE)
_DATE_RE     = re.compile(r'\b\d{1,2}[/-]\d{1,2}|\bjust\b|\brecently\b|\bthis\s+(?:week|month)\b', re.I)
_CATEGORY_RE = re.compile(
    r'\b(food|dining|groceries|transport|rent|savings?|investment|emi|shopping|entertainment)\b', re.I
)

# Tier weights for diversity bonus
_TIER_WEIGHTS = {
    MemoryTier.WORKING    : 1.15,
    MemoryTier.EPISODIC   : 1.10,
    MemoryTier.SEMANTIC   : 1.05,
    MemoryTier.PROCEDURAL : 1.08,
    MemoryTier.TRAJECTORY : 1.12,
}
_RECENCY_CUTOFF = timedelta(days=7)


class HeuristicReranker:
    """
    Lightweight post-retrieval reranker.

    Operates on already-graded GradedChunk list (post-CRAG).
    Adjusts scores without adding or removing chunks.

    Usage:
        reranker = HeuristicReranker()
        reranked = reranker.rerank(query, graded_chunks)
    """

    def rerank(
        self,
        query: str,
        graded_chunks: List[GradedChunk],
        query_tokens: Optional[List[str]] = None,
    ) -> List[GradedChunk]:
        """
        Apply heuristic re-scoring and return sorted list.

        Scoring adjustments (additive):
          + 0.15  if chunk has ≥ 2 financial entities (amounts + categories)
          + 0.10  if chunk directly matches a query keyword
          + 0.10  if episodic and created < 7 days ago
          + 0.05  source diversity bonus (penalise overrepresentation)
          + tier weight multiplier (1.05 – 1.15)

        Args:
            query: User query for keyword extraction.
            graded_chunks: CRAG-graded chunks to re-score.
            query_tokens: Pre-tokenised query (optional).

        Returns:
            Re-sorted list with updated scores.

        Example:
            >>> reranker = HeuristicReranker()
            >>> reranked = reranker.rerank("food spending trend", graded_chunks)
        """
        if not graded_chunks:
            return []

        q_lower = query.lower()
        qtoks   = set(query_tokens or _simple_tokenise(query))

        # Track tier representation for diversity penalty
        tier_counts: defaultdict[str, int] = defaultdict(int)
        for c in graded_chunks:
            tier_counts[c.source_tier.name] += 1

        rescored: List[GradedChunk] = []
        for chunk in graded_chunks:
            base_score = chunk.crag_score
            delta      = 0.0

            text = chunk.content.lower()

            # 1. Financial entity density bonus
            n_amounts    = len(_AMOUNT_RE.findall(text))
            n_categories = len(_CATEGORY_RE.findall(text))
            if n_amounts + n_categories >= 2:
                delta += 0.15
            elif n_amounts + n_categories == 1:
                delta += 0.05

            # 2. Query keyword match bonus
            chunk_toks = set(_simple_tokenise(text))
            overlap    = len(qtoks & chunk_toks)
            if overlap >= 3:
                delta += 0.10
            elif overlap >= 1:
                delta += 0.04

            # 3. Tier weight
            tier_mult = _TIER_WEIGHTS.get(chunk.source_tier, 1.0)

            # 4. Source diversity — penalise heavily-represented tiers
            tier_repr  = tier_counts.get(chunk.source_tier.name, 1)
            if tier_repr > 2 and len(graded_chunks) > 4:
                delta -= 0.05 * (tier_repr - 2)  # mild penalty per extra item

            # 5. Recency bonus for episodic (decay_score proxy)
            if chunk.source_tier == MemoryTier.EPISODIC:
                decay = chunk.metadata.get("decay_score", 0.5)
                if decay > 0.90:   # very fresh episode
                    delta += 0.10

            chunk.crag_score = round(max(0.0, min(1.5, (base_score + delta) * tier_mult)), 4)
            rescored.append(chunk)

        rescored.sort(key=lambda c: c.crag_score, reverse=True)
        logger.debug(f"[RERANKER] Reranked {len(rescored)} chunks | top={rescored[0].crag_score:.3f}")
        return rescored


def _simple_tokenise(text: str) -> List[str]:
    stops = {"i", "the", "a", "an", "is", "in", "on", "my", "to", "and", "or", "of"}
    return [t for t in re.findall(r'\b\w+\b', text.lower()) if t not in stops]
