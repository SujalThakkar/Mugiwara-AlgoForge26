"""
agents/agent_graph.py — LangGraph StateGraph for BudgetBandhu Financial Cognitive OS.

5-Node graph with conditional edges:
  START → router_node → memory_node → analysis_node → generation_node → safety_node → END
                                                      ↑ (retry loop, max 2 attempts)

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph

from database.connection import AsyncDBPool
from memory.cognitive_memory_manager import CognitiveMemoryManager
from models.schemas import BudgetBandhuAgentState, QueryIntent
from prompts.prompt_builder import ElitePromptBuilder
from rag.crag_evaluator import CRAGEvaluator
from rag.hybrid_retriever import HybridRetriever
from rag.query_router import QueryRouter
from rag.reranker import HeuristicReranker
from rag.self_rag import SelfRAGEvaluator
from safety.financial_guard import FinancialSafetyGuard
from tools.financial_toolkit import (
    budget_calculator, detect_anomalies, detect_subscriptions,
    goal_planner, scenario_engine,
)
from tools.monte_carlo import run_monte_carlo

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


# ─────────────────────────────────────────────────────────────────────────────
# NODE FUNCTIONS
# Each node receives and returns BudgetBandhuAgentState
# ─────────────────────────────────────────────────────────────────────────────

def build_agent_graph(
    pool: AsyncDBPool,
    embedding_fn=None,
) -> StateGraph:
    """
    Construct the compiled LangGraph StateGraph for BudgetBandhu.

    Nodes:
      router_node     — classify intent, determine tiers + simulation flag
      memory_node     — fetch unified 5-tier context
      analysis_node   — run deterministic FinancialToolkit tools
      generation_node — build XML prompt, call Phi-3.5, run SelfRAG
      safety_node     — constitutional screen + disclaimer injection

    Edges:
      router → memory → analysis → generation → (retry? → generation | safety) → END

    Args:
        pool: Async DB connection pool (pre-initialised).
        embedding_fn: Optional embedding callable for semantic retrieval.

    Returns:
        Compiled LangGraph graph ready for .invoke() / .ainvoke().

    Example:
        >>> graph = build_agent_graph(pool, embed_fn)
        >>> result = await graph.ainvoke(initial_state)
    """
    # Shared components
    memory_mgr  = CognitiveMemoryManager(pool, embedding_fn)
    router      = QueryRouter(embedding_fn)
    retriever   = HybridRetriever(memory_mgr, embedding_fn)
    crag        = CRAGEvaluator(embedding_fn)
    reranker    = HeuristicReranker()
    selfrag     = SelfRAGEvaluator()
    builder     = ElitePromptBuilder()
    guard       = FinancialSafetyGuard()

    # ── Node 1: Router ────────────────────────────────────────────────────────
    async def router_node(state: BudgetBandhuAgentState) -> BudgetBandhuAgentState:
        logger.info(f"[GRAPH:router] query='{state.query[:60]}'")
        decision = await router.route(state.query, state.user_id)
        state.route_decision = decision
        state.query_intent   = decision.intent
        return state

    # ── Node 2: Memory ────────────────────────────────────────────────────────
    async def memory_node(state: BudgetBandhuAgentState) -> BudgetBandhuAgentState:
        logger.info(f"[GRAPH:memory] intent={state.query_intent}")
        ctx = await memory_mgr.get_unified_context(
            state.user_id, state.query,
            state.query_intent or QueryIntent.FULL_ADVISORY,
            state.session_id,
        )
        state.memory_context = ctx

        # Hybrid retrieval + CRAG + rerank
        tiers = state.route_decision.tiers_to_query if state.route_decision else [1, 2, 3]
        raw_chunks    = await retriever.retrieve(state.query, state.user_id, tiers, top_k=12)
        graded_chunks = await crag.evaluate_chunks(state.query, raw_chunks)
        state.graded_chunks = reranker.rerank(state.query, graded_chunks)
        return state

    # ── Node 3: Analysis ──────────────────────────────────────────────────────
    async def analysis_node(state: BudgetBandhuAgentState) -> BudgetBandhuAgentState:
        logger.info("[GRAPH:analysis]")
        snapshot = getattr(state, "snapshot", None)
        use_sim  = state.route_decision.use_simulation if state.route_decision else False

        if snapshot and use_sim:
            import asyncio, functools
            loop = asyncio.get_event_loop()

            from models.schemas import SimulationResult
            sim = SimulationResult()

            if snapshot.monthly_income > 0:
                sim.budget = await loop.run_in_executor(
                    None, budget_calculator,
                    snapshot.monthly_income, snapshot.monthly_expenses
                )
            if snapshot.transactions:
                sim.anomalies      = await loop.run_in_executor(None, detect_anomalies, snapshot.transactions)
                sim.subscriptions  = await loop.run_in_executor(None, detect_subscriptions, snapshot.transactions)
            if sim.budget and sim.budget.surplus_deficit > 0 and snapshot.active_goals:
                for g in snapshot.active_goals[:3]:
                    plan = await loop.run_in_executor(
                        None, goal_planner,
                        g.get("target_amount", 100000),
                        g.get("current_amount", 0),
                        sim.budget.surplus_deficit,
                        None,
                    )
                    sim.goal_plans.append(plan)

            state.simulation_result = sim
        return state

    # ── Node 4: Generation ────────────────────────────────────────────────────
    async def generation_node(state: BudgetBandhuAgentState) -> BudgetBandhuAgentState:
        logger.info(f"[GRAPH:generation] attempt={state.generation_attempts + 1}")
        import httpx

        prompt = builder.build(
            state.query,
            state.memory_context,
            state.simulation_result,
            retry_instruction=state.retry_instruction,
            graded_chunks=state.graded_chunks,
        )
        state.prompt_used = prompt

        # Call Ollama
        payload = {
            "model": "phi3.5",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 512},
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("http://localhost:11434/api/generate", json=payload)
                resp.raise_for_status()
                state.raw_response = resp.json().get("response", "").strip()
        except Exception as e:
            logger.error(f"[GRAPH:generation] Ollama error: {e}")
            state.raw_response = "I'm having trouble generating a response. Please try again."
            state.selfrag_verdict = None
            return state

        # SelfRAG evaluation
        ctx_str = crag.get_injectable_content(state.graded_chunks or [])
        verdict = await selfrag.evaluate_response(
            state.query,
            state.query_intent or QueryIntent.FULL_ADVISORY,
            ctx_str,
            state.raw_response,
            state.graded_chunks or [],
        )
        state.selfrag_verdict = verdict
        state.generation_attempts += 1

        if not verdict.passed:
            state.retry_instruction = verdict.retry_instruction
        return state

    # ── Node 5: Safety ────────────────────────────────────────────────────────
    async def safety_node(state: BudgetBandhuAgentState) -> BudgetBandhuAgentState:
        logger.info("[GRAPH:safety]")
        confidence = (
            state.selfrag_verdict.grounded_score
            if state.selfrag_verdict else 0.5
        )
        state.screened_response = guard.screen(
            state.raw_response or "",
            confidence_score=confidence,
            query_intent=state.query_intent.value if state.query_intent else None,
        )

        # Async write-back (non-blocking)
        import asyncio
        asyncio.create_task(_write_back_memory(memory_mgr, state))
        return state

    # ── Conditional edge: generation → retry | safety ─────────────────────────
    def should_retry(state: BudgetBandhuAgentState) -> str:
        """Retry if SelfRAG failed and we haven't exceeded max retries."""
        if (
            state.selfrag_verdict
            and not state.selfrag_verdict.passed
            and state.generation_attempts <= _MAX_RETRIES
        ):
            logger.info(f"[GRAPH] Retrying generation (attempt {state.generation_attempts})")
            return "retry"
        return "safety"

    # ── Graph construction ────────────────────────────────────────────────────
    graph = StateGraph(BudgetBandhuAgentState)

    graph.add_node("router",     router_node)
    graph.add_node("memory",     memory_node)
    graph.add_node("analysis",   analysis_node)
    graph.add_node("generation", generation_node)
    graph.add_node("safety",     safety_node)

    graph.add_edge(START,        "router")
    graph.add_edge("router",     "memory")
    graph.add_edge("memory",     "analysis")
    graph.add_edge("analysis",   "generation")

    graph.add_conditional_edges(
        "generation",
        should_retry,
        {"retry": "generation", "safety": "safety"},
    )
    graph.add_edge("safety", END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────────────────────
# WRITE-BACK HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _write_back_memory(
    memory_mgr: CognitiveMemoryManager,
    state: BudgetBandhuAgentState,
) -> None:
    """Async fire-and-forget write-back to working and episodic memory."""
    try:
        await memory_mgr.flush_working_to_episodic(state.session_id, state.user_id)
        await memory_mgr.working.add(
            session_id     = state.session_id,
            user_id        = state.user_id,
            content_type   = "query",
            content        = {
                "text": state.query[:300],
                "intent": state.query_intent.value if state.query_intent else "unknown",
            },
            importance_score = 0.6,
        )
        if state.screened_response:
            await memory_mgr.write_episodic(
                state.user_id,
                event_type = "STRATEGY_APPLIED",
                trigger    = state.query[:200],
                outcome    = (state.screened_response.screened_response or "")[:300],
                session_id = state.session_id,
            )
    except Exception as e:
        logger.warning(f"[GRAPH] Write-back error (non-fatal): {e}")
