"""
explainability/response_wrapper.py — FinalResponse builder with provenance tracking.

Wraps the screened response in a structured FinalResponse object
that includes a provenance chain showing exactly which memory tier
contributed to each piece of advice.

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from models.schemas import (
    BudgetBandhuAgentState, FinalResponse, GradedChunk, MemoryTier,
    QueryIntent, ScreenedResponse,
)

logger = logging.getLogger(__name__)


class ResponseWrapper:
    """
    Post-generation provenance builder.

    Constructs the user-facing FinalResponse with:
    - Formatted response text
    - Provenance: which tiers contributed, which chunks were used
    - Confidence tier (HIGH / MEDIUM / LOW)
    - Structured metadata for frontend display
    - Follow-up question suggestions

    Usage:
        wrapper = ResponseWrapper()
        final = wrapper.wrap(state)
    """

    def wrap(self, state: BudgetBandhuAgentState) -> FinalResponse:
        """
        Build a FinalResponse from the completed pipeline state.

        Args:
            state: Completed BudgetBandhuAgentState from BudgetBandhuPipeline.run()

        Returns:
            FinalResponse ready for API serialisation.

        Example:
            >>> final = wrapper.wrap(state)
            >>> final.confidence_tier
            'HIGH'
            >>> final.provenance["tiers_used"]
            ['EPISODIC', 'SEMANTIC', 'TRAJECTORY']
        """
        screened = state.screened_response
        if not screened:
            return _error_response(state, "No screened response available.")

        # ── Confidence tier ───────────────────────────────────────────────────
        selfrag = state.selfrag_verdict
        if selfrag:
            avg_score = (
                selfrag.grounded_score
                + selfrag.retrieval_used_score
                + (1.0 - selfrag.hallucination_score)
                + selfrag.usefulness_score
            ) / 4.0
        else:
            avg_score = 0.5

        if avg_score >= 0.75:
            confidence_tier = "HIGH"
        elif avg_score >= 0.45:
            confidence_tier = "MEDIUM"
        else:
            confidence_tier = "LOW"

        # ── Provenance ────────────────────────────────────────────────────────
        tiers_used: List[str] = []
        chunks_kept_ids: List[str] = []
        chunks_discarded_count = 0

        ctx = state.memory_context
        if ctx:
            if ctx.working:
                tiers_used.append("WORKING")
            if ctx.episodic:
                tiers_used.append("EPISODIC")
            if ctx.semantic:
                tiers_used.append("SEMANTIC")
            if ctx.graph_paths:
                tiers_used.append("KNOWLEDGE_GRAPH")
            if ctx.procedural:
                tiers_used.append("PROCEDURAL")
            if ctx.trajectory:
                tiers_used.append("TRAJECTORY")

        for chunk in (state.graded_chunks or []):
            if chunk.decision in ("KEEP", "TRIM"):
                chunks_kept_ids.append(chunk.chunk_id)
            else:
                chunks_discarded_count += 1

        # ── Simulation summary ────────────────────────────────────────────────
        sim_summary: Optional[Dict] = None
        sim = state.simulation_result
        if sim:
            sim_summary = {}
            if sim.budget:
                sim_summary["savings_rate"] = f"{sim.budget.savings_rate:.1%}"
                sim_summary["surplus"]      = f"Rs.{sim.budget.surplus_deficit:,.0f}"
            if sim.monte_carlo:
                sim_summary["goal_p50_months"] = sim.monte_carlo.p50_months
                sim_summary["goal_p90_months"] = sim.monte_carlo.p90_months
            if sim.anomalies:
                sim_summary["anomalies_detected"] = len(sim.anomalies)
            if sim.subscriptions:
                sim_summary["subscriptions_found"] = len(sim.subscriptions)

        # ── Follow-up suggestions ─────────────────────────────────────────────
        followups = _generate_followups(state.query_intent, sim)

        # ── Performance metrics ───────────────────────────────────────────────
        perf = {
            "total_pipeline_ms" : round(state.total_pipeline_ms or 0, 1),
            "memory_retrieval_ms": round(ctx.retrieval_time_ms if ctx else 0, 1),
            "tiers_loaded"      : ctx.tiers_loaded if ctx else [],
            "tokens_estimated"  : ctx.total_tokens_estimated if ctx else 0,
            "selfrag_passed"    : selfrag.passed if selfrag else True,
            "generation_attempts": getattr(state, "generation_attempts", 1),
        }

        provenance = {
            "tiers_used"          : tiers_used,
            "chunks_kept"         : chunks_kept_ids,
            "chunks_discarded"    : chunks_discarded_count,
            "simulation_used"     : sim is not None,
            "safety_modifications": screened.modifications_made,
            "disclaimers_injected": screened.disclaimers_injected,
            "flagged_for_review"  : screened.flagged_for_review,
        }

        return FinalResponse(
            response_text     = screened.screened_response,
            confidence_tier   = confidence_tier,
            confidence_score  = round(avg_score, 3),
            provenance        = provenance,
            simulation_summary= sim_summary,
            follow_up_questions= followups,
            performance       = perf,
        )


def _generate_followups(
    intent: Optional[QueryIntent],
    sim: Optional[object],
) -> List[str]:
    """Suggest 2-3 relevant follow-up questions based on intent and findings."""
    if not intent:
        return []

    base_followups: Dict[QueryIntent, List[str]] = {
        QueryIntent.SIMPLE_LOOKUP: [
            "Show me my spending trend over the last 3 months",
            "Which category am I overspending on most?",
        ],
        QueryIntent.TREND_ANALYSIS: [
            "What would happen if I cut my top expense by 20%?",
            "Am I on track for my savings goal?",
        ],
        QueryIntent.GOAL_PLANNING: [
            "What if I increase my monthly savings by Rs.2,000?",
            "Simulate the impact of a 10% income raise on my goal timeline",
        ],
        QueryIntent.SCENARIO_SIM: [
            "What is my current savings rate?",
            "Show my top 3 spending categories this month",
        ],
        QueryIntent.BEHAVIORAL: [
            "What strategies have worked best for me so far?",
            "Can you create a weekend spending budget for me?",
        ],
        QueryIntent.FULL_ADVISORY: [
            "What single change would improve my finances the most?",
            "Am I building an adequate emergency fund?",
        ],
    }

    followups = base_followups.get(intent, [])

    # Add anomaly-driven follow-up if anomalies found
    if sim and hasattr(sim, "anomalies") and sim.anomalies:
        followups.append("Explain the top anomaly in my recent transactions")

    return followups[:3]


def _error_response(state: BudgetBandhuAgentState, reason: str) -> FinalResponse:
    return FinalResponse(
        response_text    = "I encountered an issue generating your response. Please try again.",
        confidence_tier  = "LOW",
        confidence_score = 0.0,
        provenance       = {"error": reason},
        simulation_summary= None,
        follow_up_questions= [],
        performance      = {},
    )
