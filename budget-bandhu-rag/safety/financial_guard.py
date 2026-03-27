"""
safety/financial_guard.py — Constitutional financial safety layer.

Post-generation screen for harmful, irresponsible, or legally problematic advice.
BudgetBandhu is NOT SEBI-registered. This guard enforces that boundary.

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from models.schemas import ScreenedResponse

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

_PROHIBITED_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bguaranteed? returns?\b', re.I),
     "guaranteed_returns"),
    (re.compile(r'\btake a loan\s+(to|for)\s+invest', re.I),
     "loan_for_investment"),
    (re.compile(r'\bbuy\s+(?:now|immediately)\s+(?:this\s+)?stock', re.I),
     "specific_stock_pick"),
    (re.compile(r'\b(?:bitcoin|eth|crypto|nft)\s+(?:will|is going to)\s+(?:rise|moon|explode)', re.I),
     "crypto_guarantee"),
]

_SOFT_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bguaranteed?\b', re.I),      "projected"),
    (re.compile(r'\bwill definitely\b', re.I),  "is likely to"),
    (re.compile(r'\bcertain(?:ly)?\b', re.I),   "likely"),
    (re.compile(r'\b100%\s+safe\b', re.I),      "generally low-risk"),
]

_DISCLAIMER_TRIGGERS: Dict[str, Tuple[re.Pattern, str]] = {
    "investment": (
        re.compile(r'\b(invest|mutual fund|sip|etf|stock|equity|nifty|sensex)\b', re.I),
        "This is for informational purposes only and not SEBI-registered investment advice. Please consult a registered investment advisor before making investment decisions."
    ),
    "insurance": (
        re.compile(r'\b(insurance|term plan|life cover|health cover|premium)\b', re.I),
        "Please consult a licensed insurance advisor for personalised coverage recommendations."
    ),
    "tax": (
        re.compile(r'\b(tax|tds|gst|itr|section 80|hra|80c)\b', re.I),
        "Tax laws vary by individual situation. Consult a Chartered Accountant (CA) or tax professional for your specific case."
    ),
    "crypto": (
        re.compile(r'\b(crypto|bitcoin|ethereum|nft|web3|defi)\b', re.I),
        "Cryptocurrency investments are highly volatile and unregulated in India. RBI advises caution. This is not investment advice."
    ),
}

_HIGH_STAKES_PATTERNS = re.compile(
    r'\b(loan|borrow|mortgage|emi|bankruptcy|default|insolvency)\b', re.I
)


class FinancialSafetyGuard:
    """
    Constitutional safety layer.

    Screens every generated response for:
    1. Prohibited content patterns
    2. Soft replacements (guaranteed -> projected)
    3. Required regulatory disclaimers
    4. High-stakes + low-confidence flagging

    Usage:
        guard = FinancialSafetyGuard()
        screened = guard.screen(response, confidence_score=0.4)
    """

    def screen(
        self,
        response: str,
        confidence_score: float = 0.8,
        query_intent: Optional[str] = None,
    ) -> ScreenedResponse:
        """
        Apply all safety checks to a generated response.

        Args:
            response: Raw generated response string.
            confidence_score: Model confidence (0-1). Low + high-stakes triggers review flag.
            query_intent: Optional, used for context-aware disclaimer injection.

        Returns:
            ScreenedResponse with modifications noted.

        Example:
            >>> screened = guard.screen("This mutual fund will give guaranteed 20% returns.", 0.9)
            >>> "projected" in screened.screened_response
            True
            >>> screened.disclaimers_injected
            ['investment']
        """
        screened = response
        modifications: List[str] = []
        disclaimers_added: List[str] = []
        flag_review = False
        flag_reason: Optional[str] = None

        # ── 1. Prohibited pattern detection ───────────────────────────────────
        for pattern, label in _PROHIBITED_PATTERNS:
            if pattern.search(screened):
                logger.warning(f"[SAFETY] Prohibited content detected: {label}")
                modifications.append(f"prohibited:{label}")
                # Replace with safe version
                screened = pattern.sub(
                    f"[NOTE: This type of advice has been filtered — {label.replace('_', ' ')}]",
                    screened
                )

        # ── 2. Soft replacements (certainty language) ──────────────────────
        for pattern, replacement in _SOFT_REPLACEMENTS:
            if pattern.search(screened):
                screened = pattern.sub(replacement, screened)
                modifications.append(f"softened:{pattern.pattern[:20]}")

        # ── 3. Regulatory disclaimers ─────────────────────────────────────────
        for topic, (trigger_pattern, disclaimer_text) in _DISCLAIMER_TRIGGERS.items():
            if trigger_pattern.search(screened):
                if disclaimer_text not in screened:
                    screened += f"\n\n[DISCLOSURE] {disclaimer_text}"
                    disclaimers_added.append(topic)

        # ── 4. High-stakes + low confidence → flag for review ─────────────────
        if confidence_score < 0.3 and _HIGH_STAKES_PATTERNS.search(screened):
            flag_review = True
            flag_reason = (
                f"Low confidence ({confidence_score:.0%}) on high-stakes topic (loans/debt). "
                "Human review recommended before acting on this advice."
            )
            screened += "\n\n[IMPORTANT] This response has low confidence due to limited user data. Please verify with a financial professional."

        if modifications or disclaimers_added:
            logger.info(
                f"[SAFETY] Modifications: {modifications} | "
                f"Disclaimers: {disclaimers_added} | Flag: {flag_review}"
            )

        return ScreenedResponse(
            original_response  = response,
            screened_response  = screened,
            modifications_made = modifications,
            disclaimers_injected= disclaimers_added,
            flagged_for_review = flag_review,
            flag_reason        = flag_reason,
        )
