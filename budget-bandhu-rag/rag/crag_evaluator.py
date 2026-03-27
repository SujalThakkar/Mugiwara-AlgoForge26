"""
rag/crag_evaluator.py — Corrective RAG: self-grading chunk scorer.

Evaluates each retrieved chunk for relevance to the query WITHOUT an LLM.
Uses 3 lightweight heuristics combined in a weighted score.

Scoring formula:
  crag_score = 0.3 * token_overlap + 0.5 * semantic_similarity + 0.2 * entity_match

Actions by score:
  > 0.7  → KEEP (inject as-is)
  0.3-0.7 → TRIM (extract high-overlap sentences)
  ≤ 0.3  → DISCARD (optionally trigger live data fallback)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Callable, List, Optional, Tuple

import httpx
import numpy as np

from models.schemas import GradedChunk, MemoryTier, RetrievedChunk

logger = logging.getLogger(__name__)

_KEEP_THRESHOLD    = 0.70
_PARTIAL_THRESHOLD = 0.30

# Indian financial entity patterns
_MONEY_PATTERN    = re.compile(r'₹[\d,]+|Rs\.?\s*[\d,]+|\d+\s*rupees?', re.IGNORECASE)
_DATE_PATTERN     = re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b', re.IGNORECASE)
_CATEGORY_PATTERN = re.compile(
    r'\b(food|groceries|transport|rent|utilities|entertainment|savings?|'
    r'investment|insurance|emi|shopping|medical|education|dining|fuel)\b',
    re.IGNORECASE,
)


class CRAGEvaluator:
    """
    Corrective RAG chunk grader.

    Usage:
        evaluator = CRAGEvaluator(embedding_fn=embed_fn)
        graded = await evaluator.evaluate_chunks(query, chunks, query_embedding)
    """

    def __init__(self, embedding_fn: Optional[Callable] = None):
        self._embed = embedding_fn

    async def evaluate_chunks(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        query_embedding: Optional[np.ndarray] = None,
    ) -> List[GradedChunk]:
        """
        Score and classify all retrieved chunks.

        Args:
            query: Original user query.
            chunks: Raw retrieved chunks from HybridRetriever.
            query_embedding: Pre-computed query embedding (optional, avoids re-embedding).

        Returns:
            List of GradedChunk with KEEP/TRIM/DISCARD decisions, sorted by crag_score DESC.

        Example:
            >>> graded = await evaluator.evaluate_chunks("food spend trend", chunks)
            >>> [c.decision for c in graded]
            ['KEEP', 'KEEP', 'TRIM', 'DISCARD']
        """
        if not chunks:
            return []

        query_tokens = _tokenise(query)

        # Compute query embedding once if not supplied
        if query_embedding is None and self._embed:
            try:
                loop = asyncio.get_event_loop()
                vec  = await loop.run_in_executor(None, self._embed, query)
                query_embedding = np.array(vec, dtype=np.float32)
            except Exception:
                query_embedding = None

        graded: List[GradedChunk] = []
        for chunk in chunks:
            token_overlap = _compute_token_overlap(query_tokens, chunk.content)
            entity_match  = _compute_entity_match(query, chunk.content)
            semantic_sim  = _compute_semantic_sim(query_embedding, chunk.embedding)

            crag_score = (
                0.3 * token_overlap
                + 0.5 * semantic_sim
                + 0.2 * entity_match
            )

            if crag_score > _KEEP_THRESHOLD:
                decision         = "KEEP"
                trimmed_content  = None
            elif crag_score > _PARTIAL_THRESHOLD:
                decision         = "TRIM"
                trimmed_content  = _trim_to_best_sentences(query_tokens, chunk.content)
            else:
                decision         = "DISCARD"
                trimmed_content  = None

            graded.append(
                GradedChunk(
                    chunk_id           = chunk.chunk_id,
                    source_tier        = chunk.source_tier,
                    content            = chunk.content,
                    original_score     = chunk.score,
                    crag_score         = round(crag_score, 4),
                    token_overlap      = round(token_overlap, 4),
                    semantic_similarity= round(semantic_sim, 4),
                    entity_match       = round(entity_match, 4),
                    decision           = decision,
                    trimmed_content    = trimmed_content,
                    metadata           = chunk.metadata,
                )
            )

        graded.sort(key=lambda c: c.crag_score, reverse=True)
        kept  = sum(1 for c in graded if c.decision == "KEEP")
        trim  = sum(1 for c in graded if c.decision == "TRIM")
        disc  = sum(1 for c in graded if c.decision == "DISCARD")
        logger.info(f"[CRAG] KEEP={kept} TRIM={trim} DISCARD={disc} of {len(graded)}")

        return graded

    def get_injectable_content(self, graded_chunks: List[GradedChunk]) -> str:
        """
        Build the final context string from graded chunks.

        Uses `trimmed_content` for TRIM decisions, full `content` for KEEP.
        DISCARD chunks are excluded entirely.

        Returns:
            Single newline-separated context string ready for prompt injection.
        """
        lines: List[str] = []
        for chunk in graded_chunks:
            if chunk.decision == "KEEP":
                lines.append(chunk.content)
            elif chunk.decision == "TRIM" and chunk.trimmed_content:
                lines.append(chunk.trimmed_content)
        return "\n".join(lines)

    async def fetch_web_fallback(self, query_intent: str) -> Optional[str]:
        """
        Called when all primary chunks score below 0.3.
        Fetches: RBI repo rate, CPI inflation estimate, Sensex level.
        Returns a formatted fallback context string.
        Only triggered for TREND_ANALYSIS and FULL_ADVISORY intents.

        Returns None on any network failure (fail silently).
        """
        if query_intent not in ("TREND_ANALYSIS", "FULL_ADVISORY"):
            return None

        fallback_url = "https://query2.finance.yahoo.com/v8/finance/chart/^BSESN?range=1d&interval=1d"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(fallback_url)
                resp.raise_for_status()
                data  = resp.json()
                price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
                return (
                    f"[LIVE MARKET] BSE Sensex: ₹{price:,.2f} (today)\n"
                    f"[NOTE] RBI repo rate: 6.50% (as of 2025 Q4). "
                    f"CPI inflation: ~5.1% (approx). Use these for advisory context only."
                )
        except Exception as e:
            logger.debug(f"[CRAG] Web fallback failed: {e}")
            return None


# ─────────────────────────────────────────────────────────────────────────────
# SCORING FUNCTIONS (pure, deterministic)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_token_overlap(query_tokens: List[str], chunk_text: str) -> float:
    """Jaccard-style: |query_tokens ∩ chunk_tokens| / |query_tokens|."""
    if not query_tokens:
        return 0.0
    chunk_tokens = set(_tokenise(chunk_text))
    shared = sum(1 for t in query_tokens if t in chunk_tokens)
    return shared / len(query_tokens)


def _compute_entity_match(query: str, chunk_text: str) -> float:
    """
    Score 0–1 based on how many financial entity types are shared.
    Checks: ₹ amounts, dates, and category keywords.
    """
    score = 0.0
    weight = 1.0 / 3.0

    if _MONEY_PATTERN.search(query) and _MONEY_PATTERN.search(chunk_text):
        score += weight
    if _DATE_PATTERN.search(query) and _DATE_PATTERN.search(chunk_text):
        score += weight

    q_cats    = set(m.group(0).lower() for m in _CATEGORY_PATTERN.finditer(query))
    c_cats    = set(m.group(0).lower() for m in _CATEGORY_PATTERN.finditer(chunk_text))
    if q_cats and c_cats and q_cats & c_cats:
        score += weight

    return min(1.0, score)


def _compute_semantic_sim(
    query_emb: Optional[np.ndarray], chunk_emb_blob: Optional[bytes]
) -> float:
    """
    Cosine similarity if both embeddings are available.
    Falls back to 0.5 (neutral) if either is missing.
    """
    if query_emb is None or not chunk_emb_blob:
        return 0.5

    try:
        import pickle
        chunk_emb = pickle.loads(chunk_emb_blob)
        chunk_arr = np.array(chunk_emb, dtype=np.float32)
        denom = np.linalg.norm(query_emb) * np.linalg.norm(chunk_arr)
        return float(np.dot(query_emb, chunk_arr) / denom) if denom > 1e-9 else 0.0
    except Exception:
        return 0.5


def _trim_to_best_sentences(query_tokens: List[str], text: str) -> str:
    """
    Extract the 2 highest-scoring sentences from a chunk.
    Uses per-sentence token overlap score.
    """
    sentences = re.split(r'[.!?|→]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return text[:200]

    scored = [
        (sum(1 for t in query_tokens if t in s.lower()), s)
        for s in sentences
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return " ".join(s for _, s in scored[:2])


def _tokenise(text: str) -> List[str]:
    stops = {"i", "the", "a", "an", "is", "in", "on", "my", "me", "did",
             "do", "to", "and", "or", "how", "much", "what", "why", "of"}
    return [t for t in re.findall(r'\b\w+\b', text.lower()) if t not in stops]
