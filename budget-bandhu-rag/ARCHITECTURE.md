# BudgetBandhu — Financial Cognitive OS Architecture

## System Overview

BudgetBandhu is a **production-grade Financial Cognitive OS** for Indian personal finance. It combines a 5-tier memory architecture with a 4-technique RAG pipeline, deterministic financial tools, and a behavioral intelligence layer — all orchestrated via LangGraph.

---

## Architecture Diagram

```
User Query
     │
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LangGraph StateGraph                            │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌────────────┐   ┌─────────────┐   │
│  │  router  │──▶│  memory  │──▶│  analysis  │──▶│ generation  │   │
│  │  _node   │   │  _node   │   │  _node     │   │  _node      │──┐│
│  └──────────┘   └──────────┘   └────────────┘   └─────────────┘  ││
│                                                         ▲  retry  ││
│                                                         └──────────┘│
│                                                   ┌─────────────┐  │
│                                                   │  safety     │  │
│                                                   │  _node      │  │
│                                                   └──────┬──────┘  │
└──────────────────────────────────────────────────────────┼─────────┘
                                                           │
                                                    FinalResponse
```

---

## Component Map

### 1. Query Router (`rag/query_router.py`)
- **Stage 1**: keyword pattern matching (6 intent classes, O(1))
- **Stage 2**: embedding similarity fallback with lazy seed precomputation
- **Intents**: SIMPLE_LOOKUP → TREND_ANALYSIS → GOAL_PLANNING → SCENARIO_SIM → BEHAVIORAL → FULL_ADVISORY

### 2. 5-Tier Cognitive Memory (`memory/`)

| Tier | Module | What it stores | Key mechanism |
|------|--------|----------------|---------------|
| 1 — Working | `working_memory.py` | Active session context | TTL eviction, token budget |
| 2 — Episodic | `episodic_memory.py` | Financial events | Decay: 0.95^days, embedding similarity |
| 3 — Semantic | `semantic_memory.py` | User profile facts | Bayesian confidence upsert |
| 3b — Graph | `knowledge_graph.py` | Entity relationships | 2-hop SQLite traversal |
| 4 — Procedural | `procedural_memory.py` | Advice strategies | EMA success rate (α=0.3) |
| 5 — Trajectory | `trajectory_memory.py` | Behavioral snapshots | 6-class deterministic archetype |

**Archetypes**: disciplined_saver · impulse_spender · volatile_spender · income_anxious · goal_oriented · unknown

### 3. Hybrid Retrieval (`rag/hybrid_retriever.py`)
Three parallel retrieval methods merged via **Reciprocal Rank Fusion (RRF)**:
```
score(d) = Σ  1 / (rank_method(d) + 60)
```
- **Vector**: cosine similarity over embedded episodic + semantic memories
- **BM25**: pure-Python IDF-weighted keyword retrieval (k1=1.5, b=0.75)
- **Graph**: multi-hop knowledge graph path strings

### 4. CRAG Evaluator (`rag/crag_evaluator.py`)
Per-chunk scoring without LLM calls:
```
crag_score = 0.3 × token_overlap + 0.5 × semantic_similarity + 0.2 × entity_match
```
- **KEEP** (>0.7): inject as-is
- **TRIM** (0.3–0.7): extract best 2 sentences
- **DISCARD** (<0.3): trigger web fallback if all chunks fail

### 5. Deterministic Financial Toolkit (`tools/financial_toolkit.py`)
**Zero LLM arithmetic.** All numbers from here:

| Function | What it computes |
|----------|-----------------|
| `budget_calculator` | 50/30/20 compliance, surplus/deficit, ranked cuts |
| `goal_planner` | months-to-goal, required monthly contribution, milestone schedule |
| `scenario_engine` | diff vs baseline for hypothetical changes |
| `detect_anomalies` | Z-score per category + duplicate + odd-hour detection |
| `detect_subscriptions` | recurring charge pattern detection |

### 6. Monte Carlo Engine (`tools/monte_carlo.py`)
- 1,000 vectorised NumPy trajectories in **<50ms**
- Returns p50 / p75 / p90 months to goal
- Binary-search for 90% confidence contribution target

### 7. XML Prompt Builder (`prompts/prompt_builder.py`)
- Strict **2,800-token budget** (≈11,200 characters)
- Structured XML sections: `<SYSTEM>` → `<USER_PROFILE>` → `<TRAJECTORY>` → `<PROCEDURAL_STRATEGY>` → `<ANALYSIS>` → `<USER_DATA>` → `<QUERY>`
- Graceful trimming: drops KNOWLEDGE_GRAPH first, then trims EPISODES, then trims TRAJECTORY

### 8. SelfRAG Evaluator (`rag/self_rag.py`)
Post-generation 4-criterion quality gate — zero LLM calls:

| Criterion | Check |
|-----------|-------|
| GROUNDED | Response cites ₹ amounts from context (±20% tolerance) |
| RETRIEVAL_USED | Contains user-specific facts, not generic advice |
| NO_HALLUCINATION | No amounts 10× outside context range or certain future claims |
| USEFUL | Answer type matches intent (number for LOOKUP, direction for TREND, etc.) |

Up to 2 automatic retries with targeted fix instruction.

### 9. Constitutional Safety Guard (`safety/financial_guard.py`)
- Prohibited pattern detection: guaranteed returns, loan-for-investment, specific stock picks
- Soft replacement: "guaranteed" → "projected", "certainly" → "likely"
- Regulatory disclaimers: SEBI (investment), IRDA (insurance), CA (tax), RBI (crypto)
- Low-confidence + high-stakes → flagged for human review

### 10. Causal Engine (`causal/causal_engine.py`)
Rule-based counterfactual reasoning:
- OVERSPEND → category causal chain → specific fix
- SAVINGS_FAIL → income shock vs expense creep vs goal misalignment
- GOAL_DELAY → contribution shortfall vs one-time expenses vs income decline

---

## Database Schema (7 tables, SQLite WAL)

```
working_memory          — Tier 1 session context (TTL)
episodic_memory         — Tier 2 events with decay_score
semantic_memory         — Tier 3 user profile facts (UNIQUE constraint)
knowledge_graph_edges   — Tier 3b relationship edges
procedural_memory       — Tier 4 strategy bank
trajectory_memory       — Tier 5 weekly behavioral snapshots
retrieval_audit         — Full RAG pipeline audit trail
schema_migrations       — Idempotent migration tracker
```

---

## Performance Targets

| Metric | Target |
|--------|--------|
| SIMPLE_LOOKUP (no LLM) | < 200ms |
| TREND_ANALYSIS | < 3s |
| GOAL_PLANNING with Monte Carlo | < 4s |
| FULL_ADVISORY | < 8s |
| Monte Carlo (1000 paths) | < 50ms |
| Memory retrieval (all 5 tiers) | < 150ms |

---

## Indian Finance Compliance

- All amounts in ₹ (Indian Rupee) enforced at system + safety layer
- Indian numbering: 1,00,000 = 1 Lakh, 1,00,00,000 = 1 Crore
- RBI repo rate context injection in web fallback
- SEBI disclaimer for investment advice
- No guaranteed return claims (constitutional filter)
