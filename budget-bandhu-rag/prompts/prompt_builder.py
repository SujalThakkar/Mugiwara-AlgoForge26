"""
prompts/prompt_builder.py — XML-structured prompt assembly with strict token budget.

Small models (Phi-3.5, Mistral-7B) perform 30-40% better with structured XML
versus unstructured prose injection.

Token budget: 2800 tokens total (~11,200 characters).
Priority order: SYSTEM > USER_PROFILE > TRAJECTORY > PROCEDURAL > ANALYSIS > EPISODES > GRAPH

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from typing import List, Optional

from models.schemas import (
    GradedChunk, SimulationResult, UnifiedMemoryContext,
)

logger = logging.getLogger(__name__)

_MAX_CHARS   = 11_200   # 2800 tokens * ~4 chars/token
_SECTION_SEP = "\n"


SYSTEM_INSTRUCTION = (
    "You are BudgetBandhu, an elite personal finance advisor for Indian users. "
    "You reason like a Chartered Accountant with behavioral psychology expertise. "
    "ABSOLUTE RULES: "
    "1. ONLY use Indian Rupees (Rs. or the rupee sign). NEVER use $ or EUR. "
    "2. Use Indian numbering: 1,00,000 = 1 Lakh, 1,00,00,000 = 1 Crore. "
    "3. ONLY cite figures from USER_DATA or ANALYSIS blocks. Never invent numbers. "
    "4. Follow PROCEDURAL_STRATEGY tone instructions exactly. "
    "5. End EVERY response with ONE specific, immediately actionable next step. "
    "6. If confidence is LOW, begin with 'Based on limited data available...' "
    "7. Show math for any calculation you present (X - Y = Z format)."
)


class ElitePromptBuilder:
    """
    Builds XML-structured prompts for Phi-3.5/Ollama with token budget enforcement.

    Drop priority when over budget:
      1. Drop KNOWLEDGE_GRAPH section
      2. Trim EPISODES from 4 -> 2 -> 1
      3. Trim TRAJECTORY to archetype label only
      4. Never drop USER_PROFILE or PROCEDURAL_STRATEGY

    Usage:
        builder = ElitePromptBuilder()
        prompt = builder.build(query, memory_ctx, sim_result)
    """

    def build(
        self,
        query: str,
        memory_context: UnifiedMemoryContext,
        simulation_result: Optional[SimulationResult] = None,
        retry_instruction: Optional[str] = None,
        graded_chunks: Optional[List[GradedChunk]] = None,
    ) -> str:
        """
        Assemble the final prompt string.

        Args:
            query: User's natural language question.
            memory_context: 5-tier unified memory context.
            simulation_result: Optional FinancialToolkit output.
            retry_instruction: SelfRAG retry fix instruction.
            graded_chunks: CRAG-graded retrieval chunks for injection.

        Returns:
            Complete prompt string ready for Ollama /api/generate.

        Example:
            >>> prompt = builder.build("How much did I spend on food?", ctx)
            >>> len(prompt) < 12000
            True
        """
        # ── Mandatory sections (never dropped) ───────────────────────────────
        system_block      = _xml("SYSTEM", SYSTEM_INSTRUCTION)
        user_profile_block = self._build_user_profile(memory_context)

        # ── Optional sections (drop/trim under budget pressure) ──────────────
        trajectory_block  = self._build_trajectory(memory_context)
        procedural_block  = self._build_procedural(memory_context)
        analysis_block    = self._build_analysis(simulation_result)
        episodes_block    = self._build_episodes(memory_context)
        graph_block       = self._build_graph(memory_context)
        graded_block      = self._build_graded_context(graded_chunks or [])

        # ── Assemble with budget enforcement ─────────────────────────────────
        mandatory = "\n".join([system_block, user_profile_block])

        optional_sections = [
            ("trajectory",  trajectory_block),
            ("procedural",  procedural_block),
            ("analysis",    analysis_block),
            ("episodes",    episodes_block),
            ("graded",      graded_block),
            ("graph",       graph_block),
        ]

        body = mandatory
        for name, section in optional_sections:
            candidate = body + "\n" + section
            if len(candidate) <= _MAX_CHARS:
                body = candidate
            else:
                logger.debug(f"[PROMPT] Budget exceeded — dropping {name} section")
                if name in ("trajectory", "episodes"):
                    # Try trimmed version
                    trimmed = section[:max(100, ((_MAX_CHARS - len(body)) // 2))]
                    body += "\n" + trimmed
                # procedural and analysis are kept as-is if they fit; dropped if not

        # ── Query block ───────────────────────────────────────────────────────
        if retry_instruction:
            query_block = _xml("RETRY_INSTRUCTION", retry_instruction) + "\n" + _xml("QUERY", query)
        else:
            query_block = _xml("QUERY", query)

        full_prompt = body + "\n" + query_block + "\n<RESPONSE>"
        logger.info(f"[PROMPT] Built prompt: {len(full_prompt)} chars ({len(full_prompt)//4} tokens)")
        return full_prompt

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION BUILDERS
    # ──────────────────────────────────────────────────────────────────────────

    def _build_user_profile(self, ctx: UnifiedMemoryContext) -> str:
        if not ctx.semantic:
            return _xml("USER_PROFILE", "No profile data available.")
        lines = [f"  {m.attribute}: {m.value} (confidence: {m.confidence_score:.0%})"
                 for m in ctx.semantic[:3]]
        return _xml("USER_PROFILE", "\n".join(lines))

    def _build_trajectory(self, ctx: UnifiedMemoryContext) -> str:
        t = ctx.trajectory
        if not t:
            return ""
        lines = [
            f"  Behavioral archetype: {t.behavioral_archetype.value}",
        ]
        if t.savings_rate_current is not None:
            lines.append(f"  Current savings rate: {t.savings_rate_current:.1%}")
        if t.savings_rate_trend:
            lines.append(f"  Savings trend: {t.savings_rate_trend.value}")
        if t.spending_velocity_7d is not None:
            lines.append(f"  7-day spending velocity: {t.spending_velocity_7d:+.1f}%")
        if t.top_3_categories:
            lines.append(f"  Top spending categories: {', '.join(t.top_3_categories)}")
        if t.anomaly_frequency_30d:
            lines.append(f"  Anomalies last 30d: {t.anomaly_frequency_30d}")
        return _xml("TRAJECTORY", "\n".join(lines))

    def _build_procedural(self, ctx: UnifiedMemoryContext) -> str:
        p = ctx.procedural
        if not p:
            return ""
        tone = p.tone_override or "balanced"
        lines = [
            f"  Strategy: {p.strategy_id}",
            f"  Tone: {tone}",
            f"  Action: {p.action_template}",
            f"  Success rate: {p.success_rate:.0%}",
        ]
        return _xml("PROCEDURAL_STRATEGY", "\n".join(lines))

    def _build_analysis(self, sim: Optional[SimulationResult]) -> str:
        if not sim:
            return ""
        lines: List[str] = []
        if sim.budget:
            b = sim.budget
            lines.append(f"  Monthly savings rate: {b.savings_rate:.1%}")
            lines.append(f"  Surplus/deficit: Rs.{b.surplus_deficit:,.0f}")
            if b.recommended_cuts:
                top_cut = b.recommended_cuts[0]
                lines.append(f"  Top recommended cut: {top_cut[0]} by Rs.{top_cut[1]:,.0f}")
        if sim.monte_carlo:
            mc = sim.monte_carlo
            lines.append(f"  Goal p50: {mc.p50_months:.0f} months, p90: {mc.p90_months:.0f} months")
            lines.append(f"  12-month probability: {mc.probability_in_12m:.0%}")
        if sim.scenario:
            sc = sim.scenario
            lines.append(f"  Scenario new savings rate: {sc.new_savings_rate:.1%} (was {sc.baseline_savings_rate:.1%})")
        if sim.anomalies:
            lines.append(f"  Anomalies detected: {len(sim.anomalies)} (top: {sim.anomalies[0].description[:50]})")
        if sim.subscriptions:
            total_annual = sum(s.annual_cost for s in sim.subscriptions)
            lines.append(f"  Active subscriptions: {len(sim.subscriptions)}, total Rs.{total_annual:,.0f}/year")
        return _xml("ANALYSIS", "\n".join(lines)) if lines else ""

    def _build_episodes(self, ctx: UnifiedMemoryContext) -> str:
        if not ctx.episodic:
            return ""
        lines: List[str] = []
        for ep in ctx.episodic[:3]:
            amount_str = f" Rs.{ep.amount_inr:,.0f}" if ep.amount_inr else ""
            lines.append(
                f"  [{ep.event_type}]{amount_str}: {ep.trigger_description[:100]}"
                f" -> {ep.outcome_description[:80]}"
            )
        return _xml("RECENT_EPISODES", "\n".join(lines))

    def _build_graph(self, ctx: UnifiedMemoryContext) -> str:
        if not ctx.graph_paths:
            return ""
        content = "\n".join(f"  {p}" for p in ctx.graph_paths[:4])
        return _xml("KNOWLEDGE_GRAPH_INSIGHTS", content)

    def _build_graded_context(self, chunks: List[GradedChunk]) -> str:
        lines: List[str] = []
        for c in chunks:
            if c.decision == "DISCARD":
                continue
            text = c.trimmed_content or c.content
            lines.append(f"  [{c.source_tier.name}] {text[:160]}")
        if not lines:
            return ""
        return _xml("USER_DATA", "\n".join(lines[:6]))


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _xml(tag: str, content: str) -> str:
    return f"<{tag}>\n{content}\n</{tag}>"
