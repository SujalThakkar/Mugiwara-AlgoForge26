"""
rag/self_rag.py — Post-generation grounding evaluator.

Evaluates the generated response against 4 criteria WITHOUT an LLM call.
Uses deterministic rule-based checks.

Criteria:
  1. GROUNDED       — references specific ₹ amounts from context
  2. RETRIEVAL_USED — contains user-specific facts, not only generic advice
  3. NO_HALLUCINATION — no impossible claims (amounts 10× out of range, absent merchants)
  4. USEFUL          — answers the actual query type (contains number for SIMPLE_LOOKUP, etc.)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Set

from models.schemas import GradedChunk, QueryIntent, SelfRAGVerdict

logger = logging.getLogger(__name__)

_AMOUNT_RE        = re.compile(r'₹[\d,]+(?:\.\d{1,2})?|Rs\.?\s*[\d,]+', re.IGNORECASE)
_DIRECTION_WORDS  = {"increasing", "decreasing", "rising", "falling", "more", "less",
                     "higher", "lower", "up", "down", "grew", "reduced", "improved"}
_ACTION_WORDS     = {"save", "invest", "cut", "reduce", "target", "allocate",
                     "set aside", "transfer", "automate", "budget"}
_TIMELINE_WORDS   = {"month", "months", "week", "weeks", "year", "years", "by",
                     "within", "timeline", "date", "deadline"}


class SelfRAGEvaluator:
    """
    Post-generation quality gate.

    Usage:
        evaluator = SelfRAGEvaluator()
        verdict = await evaluator.evaluate_response(
            query, intent, context_str, response_str, graded_chunks
        )
        if not verdict.passed:
            # pass verdict.retry_instruction back to generation node
    """

    async def evaluate_response(
        self,
        query: str,
        query_intent: QueryIntent,
        context_injected: str,
        generated_response: str,
        graded_chunks: List[GradedChunk],
    ) -> SelfRAGVerdict:
        """
        Check 4 grounding criteria against response and context.

        Args:
            query: Original user query.
            query_intent: Classified intent (drives USEFUL check).
            context_injected: The context string that was sent to the model.
            generated_response: Raw model output.
            graded_chunks: CRAG-graded chunks (for amount extraction).

        Returns:
            SelfRAGVerdict with pass/fail and retry instruction if failed.

        Example:
            >>> verdict = await evaluator.evaluate_response(
            ...     "how much did I spend on food?",
            ...     QueryIntent.SIMPLE_LOOKUP,
            ...     "Food spending: ₹4,200 this month",
            ...     "You spent approximately ₹4,000 on food.",
            ...     graded_chunks
            ... )
            >>> verdict.passed
            True
        """
        failed: List[str] = []
        scores: dict = {}

        r = generated_response.lower()
        c = context_injected.lower()

        # ── 1. GROUNDED: Does response reference ₹ amounts from context? ────
        ctx_amounts  = set(_AMOUNT_RE.findall(context_injected))
        resp_amounts = set(_AMOUNT_RE.findall(generated_response))

        if ctx_amounts and not resp_amounts:
            failed.append("GROUNDED")
            scores["grounded"] = 0.0
        elif ctx_amounts and resp_amounts:
            # Allow ±20% from any context amount (LLM may round)
            grounded = _any_amount_in_range(ctx_amounts, resp_amounts, tolerance=0.20)
            scores["grounded"] = 1.0 if grounded else 0.5
            if not grounded and len(resp_amounts) > 0:
                # Response has amounts but none match context — potential hallucination
                failed.append("GROUNDED")
                scores["grounded"] = 0.3
        else:
            scores["grounded"] = 0.8  # no amounts expected, can't grade this way

        # ── 2. RETRIEVAL_USED: Contains specific facts, not only generic advice ──
        generic_phrases = [
            "as a general rule", "it is recommended", "in general",
            "typically", "most people", "financial experts suggest",
            "generally speaking", "it depends",
        ]
        has_generic_only = all(phrase in r for phrase in generic_phrases[:2])
        has_specific     = bool(_AMOUNT_RE.search(generated_response)) or \
                           any(word in r for word in ["your", "you spent", "you earned", "you saved"])

        if has_generic_only and not has_specific:
            failed.append("RETRIEVAL_USED")
            scores["retrieval_used"] = 0.2
        else:
            scores["retrieval_used"] = 0.9 if has_specific else 0.7

        # ── 3. NO_HALLUCINATION: Check for impossible claims ─────────────────
        hallucination_score = 0.0

        # Check amounts not 10× outside context range
        if ctx_amounts and resp_amounts:
            ctx_vals  = _extract_amounts(ctx_amounts)
            resp_vals = _extract_amounts(resp_amounts)
            if ctx_vals and resp_vals:
                max_ctx   = max(ctx_vals) * 10
                min_ctx   = min(ctx_vals) / 10
                for rv in resp_vals:
                    if rv > max_ctx or rv < min_ctx * 0.1:
                        hallucination_score = max(hallucination_score, 0.7)
                        break

        # Check for future dates stated as certain fact
        future_date_pattern = re.compile(r'\b202[7-9]\b|\b203\d\b')
        certain_future      = re.compile(r'\bwill definitely\b|\bguaranteed\b|\bcertain\b')
        if future_date_pattern.search(generated_response) and certain_future.search(generated_response):
            hallucination_score = max(hallucination_score, 0.6)

        # ── Check: fabricated Indian legal / tax section numbers ──────────────
        _VERIFIED_TAX_SECTIONS = {
            # Income Tax Act — commonly cited, verified real sections
            "80c", "80d", "80e", "80g", "80gg", "80tta", "80ttb", "87a",
            "10", "10a", "10b", "24", "24b", "44ad", "44ada", "44ae",
            "139", "139a", "143", "147", "148", "194", "194a", "194c",
            "194h", "194i", "194j", "195", "206c",
            # Penalty / prosecution sections
            "271", "271a", "271aac", "271aad", "272", "272a",
            "276", "276b", "276c", "276cc", "276ccc",
            "277", "278", "278a", "278b", "278c", "278e",
            # GST Act
            "9", "10", "15", "16", "17", "18",
            # FEMA
            "13",
        }
        _SECTION_RE = re.compile(
            r'section\s+(\d{1,3}[A-Za-z]{0,4}(?:\(\d+\))?)',
            re.IGNORECASE
        )
        for m in _SECTION_RE.finditer(generated_response):
            sec_raw   = m.group(1)
            sec_clean = re.sub(r'[^0-9a-z]', '', sec_raw.lower())
            # Flag if NOT in whitelist AND NOT present verbatim in context
            if (sec_clean not in _VERIFIED_TAX_SECTIONS
                    and sec_raw.lower() not in context_injected.lower()):
                hallucination_score = max(hallucination_score, 0.8)
                logger.warning(f"[SELF-RAG] 🚨 Unverified section cited: Section {sec_raw}")
                break

        if hallucination_score >= 0.5:
            failed.append("NO_HALLUCINATION")
        scores["hallucination"] = hallucination_score

        # ── 4. USEFUL: Answer matches query type ─────────────────────────────
        useful_score = _check_usefulness(r, query_intent)
        scores["useful"] = useful_score
        if useful_score < 0.4:
            failed.append("USEFUL")

        # ── Build verdict ────────────────────────────────────────────────────
        passed = len(failed) == 0

        retry_instruction: Optional[str] = None
        if not passed:
            retry_instruction = _build_retry_instruction(failed, query_intent, ctx_amounts)

        verdict = SelfRAGVerdict(
            passed              = passed,
            failed_criteria     = failed,
            retry_instruction   = retry_instruction,
            grounded_score      = scores.get("grounded", 1.0),
            retrieval_used_score= scores.get("retrieval_used", 1.0),
            hallucination_score = scores.get("hallucination", 0.0),
            usefulness_score    = scores.get("useful", 1.0),
        )

        if passed:
            logger.info("[SELF-RAG] ✅ Response passed all grounding checks")
        else:
            logger.warning(f"[SELF-RAG] ⚠️  Failed: {failed}")

        return verdict


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_amounts(amount_strings: Set[str]) -> List[float]:
    """Convert ₹ strings to float values."""
    vals: List[float] = []
    for s in amount_strings:
        clean = re.sub(r'[₹Rs.,\s]', '', s, flags=re.IGNORECASE)
        try:
            vals.append(float(clean))
        except ValueError:
            pass
    return vals


def _any_amount_in_range(
    ctx_amounts: Set[str], resp_amounts: Set[str], tolerance: float = 0.20
) -> bool:
    """Check if any response amount is within tolerance of any context amount."""
    ctx_vals  = _extract_amounts(ctx_amounts)
    resp_vals = _extract_amounts(resp_amounts)
    if not ctx_vals or not resp_vals:
        return True  # can't grade
    for rv in resp_vals:
        for cv in ctx_vals:
            if cv > 0 and abs(rv - cv) / cv <= tolerance:
                return True
    return False


def _check_usefulness(response_lower: str, intent: QueryIntent) -> float:
    """Checks if response type matches query intent."""
    if intent == QueryIntent.SIMPLE_LOOKUP:
        # Must contain a specific number or amount
        has_number = bool(re.search(r'₹[\d,]+|\d{1,3},\d{3}|\d{4,}', response_lower))
        return 0.9 if has_number else 0.2

    if intent == QueryIntent.TREND_ANALYSIS:
        has_direction = any(w in response_lower for w in _DIRECTION_WORDS)
        return 0.9 if has_direction else 0.3

    if intent == QueryIntent.GOAL_PLANNING:
        has_timeline = any(w in response_lower for w in _TIMELINE_WORDS)
        has_action   = any(w in response_lower for w in _ACTION_WORDS)
        return 0.9 if (has_timeline or has_action) else 0.3

    if intent == QueryIntent.SCENARIO_SIM:
        has_conditional = any(w in response_lower for w in ["if", "would", "could", "potentially", "projection"])
        return 0.9 if has_conditional else 0.3

    return 0.8  # BEHAVIORAL, FULL_ADVISORY — harder to grade, assume ok


def _build_retry_instruction(
    failed: List[str], intent: QueryIntent, ctx_amounts: Set[str]
) -> str:
    """Build a targeted instruction to fix the failed criteria in the next attempt."""
    parts: List[str] = ["REVISION NEEDED. Fix the following issues:"]

    if "GROUNDED" in failed:
        amounts_str = ", ".join(sorted(ctx_amounts)[:3]) or "the amounts in <USER_DATA>"
        parts.append(
            f"• You MUST cite specific ₹ amounts from the context: {amounts_str}. "
            "Do not use generic estimates."
        )
    if "RETRIEVAL_USED" in failed:
        parts.append(
            "• Your response is too generic. Reference specific user data (transactions, "
            "categories, or goals) from <USER_DATA>."
        )
    if "NO_HALLUCINATION" in failed:
        parts.append(
            "• You cited amounts or dates not supported by the context. "
            "Only use figures that appear in <USER_DATA> or <ANALYSIS>."
        )
    if "USEFUL" in failed:
        if intent == QueryIntent.SIMPLE_LOOKUP:
            parts.append("• Provide a specific numerical answer.")
        elif intent == QueryIntent.TREND_ANALYSIS:
            parts.append("• Include a directional statement (increasing/decreasing).")
        elif intent == QueryIntent.GOAL_PLANNING:
            parts.append("• Include a timeline (months/weeks) and a concrete action step.")

    return " ".join(parts)
