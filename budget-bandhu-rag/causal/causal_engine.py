"""
causal/causal_engine.py — Lightweight counterfactual / causal reasoning engine.

Determines CAUSE of financial events using rule chains over structured data.
No LLM. No external ML model. Pure deterministic logic.

Taxonomy of causal chains (expandable):
  OVERSPEND    → category spike → subcausal lookup → recommendation
  SAVINGS_FAIL → income shock | expense creep | goal misalignment
  GOAL_DELAY   → contribution shortfall | one-time expense | income reduction

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from models.schemas import (
    CausalFinding, EpisodicMemory, FinancialSnapshot,
    TrajectoryMemory,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL RULES
# ─────────────────────────────────────────────────────────────────────────────

_OVERSPEND_CAUSES: List[Tuple[str, str, str]] = [
    # (condition, cause_label, recommendation)
    ("food",          "CATEGORY_SPIKE",    "Set a daily dining budget. Use a UPI subcategory limit."),
    ("shopping",      "IMPULSE_PURCHASE",  "Implement a 24-hour waiting rule before non-essential purchases."),
    ("entertainment", "LIFESTYLE_CREEP",   "Review subscriptions. Cancel services used < 2×/month."),
    ("transport",     "COMMUTE_COST",      "Evaluate monthly pass vs per-ride cost for your routes."),
    ("medical",       "EMERGENCY_EXPENSE", "Build a Rs.10,000 medical buffer in liquid savings."),
    ("travel",        "SEASONAL_SPIKE",    "Budget annually for travel; create a dedicated travel sinking fund."),
]

_SAVINGS_FAIL_CAUSES: List[Tuple[str, float, str, str]] = [
    # (metric, threshold, cause_label, recommendation)
    ("income_stability", 0.60, "INCOME_SHOCK",      "Diversify income streams. Build a 3-month emergency fund first."),
    ("savings_rate",     0.05, "EXPENSE_CREEP",     "Automate savings via SIP on salary day. Pay yourself first."),
    ("goal_adherence",   0.50, "GOAL_MISALIGNMENT", "Break goals into monthly milestones. Review weekly for 1 month."),
]

_GOAL_DELAY_CAUSES: List[Tuple[str, str, str]] = [
    # (factor, cause_label, recommendation)
    ("low_surplus",      "CONTRIBUTION_SHORTFALL", "Identify and cut the single largest discretionary expense."),
    ("high_anomaly_freq","ONE_TIME_EXPENSES",       "Create a buffer fund of Rs.5,000 for unexpected expenses."),
    ("declining_income", "INCOME_REDUCTION",        "Prioritise stabilising income before increasing savings rate."),
]


class CausalEngine:
    """
    Rule-based causal reasoning engine for financial events.

    Analyses:
      - OVERSPEND events → specific category causal chain
      - SAVINGS_FAIL → income shock vs expense creep vs goal misalignment
      - GOAL_DELAY → contribution shortfall, irregular expenses, income reduction

    All reasoning is traceable and cite-able (no black-box).

    Usage:
        engine = CausalEngine()
        findings = engine.analyse(episodes, trajectory, snapshot)
    """

    def analyse(
        self,
        episodes: List[EpisodicMemory],
        trajectory: Optional[TrajectoryMemory],
        snapshot: Optional[FinancialSnapshot],
    ) -> List[CausalFinding]:
        """
        Run causal analysis over available data.

        Returns up to 5 ranked CausalFinding objects.

        Args:
            episodes: Recent episodic memories.
            trajectory: Latest trajectory snapshot.
            snapshot: Current financial state.

        Returns:
            List of CausalFinding sorted by confidence DESC.

        Example:
            >>> findings = engine.analyse(episodes, trajectory, snapshot)
            >>> findings[0].cause_label
            'CATEGORY_SPIKE'
        """
        findings: List[CausalFinding] = []

        # ── 1. Overspend analysis ──────────────────────────────────────────────
        overspend_episodes = [
            ep for ep in episodes
            if ep.event_type in ("OVERSPEND", "ANOMALY") and ep.category
        ]
        for ep in overspend_episodes[:3]:
            finding = self._analyse_overspend(ep)
            if finding:
                findings.append(finding)

        # ── 2. Savings failure analysis ────────────────────────────────────────
        if trajectory:
            savings_findings = self._analyse_savings_failure(trajectory)
            findings.extend(savings_findings)

        # ── 3. Goal delay analysis ─────────────────────────────────────────────
        if trajectory and snapshot and snapshot.active_goals:
            goal_findings = self._analyse_goal_delay(trajectory, snapshot)
            findings.extend(goal_findings)

        # Sort by confidence, deduplicate by cause_label
        findings.sort(key=lambda f: f.confidence, reverse=True)
        seen: set[str] = set()
        unique: List[CausalFinding] = []
        for f in findings:
            if f.cause_label not in seen:
                unique.append(f)
                seen.add(f.cause_label)

        logger.info(f"[CAUSAL] Produced {len(unique)} causal findings")
        return unique[:5]

    def _analyse_overspend(self, episode: EpisodicMemory) -> Optional[CausalFinding]:
        """Match episode category to a causal rule."""
        cat = (episode.category or "").lower()
        for rule_cat, cause_label, recommendation in _OVERSPEND_CAUSES:
            if rule_cat in cat:
                return CausalFinding(
                    event_type        = episode.event_type,
                    cause_label       = cause_label,
                    evidence          = [
                        f"{episode.trigger_description[:100]}",
                        f"Amount: Rs.{episode.amount_inr:,.0f}" if episode.amount_inr else "",
                    ],
                    counterfactual    = (
                        f"If {cat} spending had been within budget, "
                        f"Rs.{episode.amount_inr or 0:,.0f} would have been saved."
                    ),
                    recommendation    = recommendation,
                    confidence        = episode.confidence_score * episode.decay_score,
                )
        # Unknown category
        return CausalFinding(
            event_type     = episode.event_type,
            cause_label    = "UNKNOWN_CATEGORY_SPIKE",
            evidence       = [episode.trigger_description[:100]],
            counterfactual = "Tracking this category could reveal the root cause.",
            recommendation = "Categorise this expense and monitor for recurring patterns.",
            confidence     = 0.3,
        )

    def _analyse_savings_failure(
        self, trajectory: TrajectoryMemory
    ) -> List[CausalFinding]:
        """Check savings rate, income stability, and goal adherence against thresholds."""
        findings: List[CausalFinding] = []

        for metric, threshold, cause_label, recommendation in _SAVINGS_FAIL_CAUSES:
            value: Optional[float] = None
            if metric == "income_stability":
                value = trajectory.income_stability_score
            elif metric == "savings_rate":
                value = trajectory.savings_rate_current
            elif metric == "goal_adherence":
                value = trajectory.goal_adherence_score

            if value is not None and value < threshold:
                findings.append(CausalFinding(
                    event_type     = "SAVINGS_FAIL",
                    cause_label    = cause_label,
                    evidence       = [f"{metric.replace('_', ' ').title()}: {value:.0%} (below {threshold:.0%} threshold)"],
                    counterfactual = f"If {metric.replace('_', ' ')} were above {threshold:.0%}, savings target would be achievable.",
                    recommendation = recommendation,
                    confidence     = max(0.1, threshold - value),
                ))

        return findings

    def _analyse_goal_delay(
        self, trajectory: TrajectoryMemory, snapshot: FinancialSnapshot
    ) -> List[CausalFinding]:
        """Flag structural reasons a goal may be delayed."""
        findings: List[CausalFinding] = []

        total_income = snapshot.monthly_income or 0
        total_expenses = sum(snapshot.monthly_expenses.values()) if snapshot.monthly_expenses else 0
        surplus = total_income - total_expenses

        for factor, cause_label, recommendation in _GOAL_DELAY_CAUSES:
            if factor == "low_surplus" and surplus < total_income * 0.10:
                findings.append(CausalFinding(
                    event_type     = "GOAL_DELAY",
                    cause_label    = cause_label,
                    evidence       = [f"Surplus = Rs.{surplus:,.0f} ({surplus/total_income:.0%} of income)"],
                    counterfactual = f"Increasing surplus to 20% would cut goal timeline by ~50%.",
                    recommendation = recommendation,
                    confidence     = 0.75,
                ))
            elif factor == "high_anomaly_freq" and (trajectory.anomaly_frequency_30d or 0) > 3:
                findings.append(CausalFinding(
                    event_type     = "GOAL_DELAY",
                    cause_label    = cause_label,
                    evidence       = [f"Anomalies in last 30 days: {trajectory.anomaly_frequency_30d}"],
                    counterfactual = "Each anomaly interrupted consistent saving, delaying goal.",
                    recommendation = recommendation,
                    confidence     = 0.65,
                ))
            elif factor == "declining_income":
                trend = getattr(trajectory, "savings_rate_trend", None)
                if trend and hasattr(trend, "value") and trend.value == "declining":
                    findings.append(CausalFinding(
                        event_type     = "GOAL_DELAY",
                        cause_label    = cause_label,
                        evidence       = ["Savings rate trend: declining"],
                        counterfactual = "Stable income would maintain current goal trajectory.",
                        recommendation = recommendation,
                        confidence     = 0.55,
                    ))

        return findings
