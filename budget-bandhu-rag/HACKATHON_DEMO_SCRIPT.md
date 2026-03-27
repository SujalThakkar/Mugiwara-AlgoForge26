# BudgetBandhu — Hackathon Demo Script

**System**: Financial Cognitive OS v3.0  
**Model**: Phi-3.5 via Ollama  
**Key message**: This is not a chatbot. This is a Financial Operating System with memory, causal reasoning, and behavioral intelligence.

---

## Pre-Demo Setup

```bash
# Terminal 1 — Start Ollama with Phi-3.5
ollama run phi3.5

# Terminal 2 — Start backend
cd budget-bandhu-ml
python -m uvicorn api.app:app --port 8000 --reload

# Terminal 3 — Run migrations
python database/migrations.py budget_bandhu_cognitive.db
```

---

## Demo Scenario 1: Memory — "It Remembers You"

**Setup**: User has had 3 previous sessions where food overspending was flagged.

**Query**: _"Why do I keep overspending on food?"_

**What to show**:
1. Episodic memory retrieves 3 past food-overspend episodes (with decay scores)
2. Knowledge graph shows `user → OVERSPENDS_ON → food` edge strengthening over time
3. Causal engine produces: `CATEGORY_SPIKE` finding with counterfactual
4. Procedural memory selects `loss_frame_food` strategy (analytical tone)

**Talking point**: _"Unlike ChatGPT, BudgetBandhu remembers that this is the third time you've come with the same problem. Its advice gets sharper every session."_

---

## Demo Scenario 2: Deterministic Math — "Zero LLM Arithmetic"

**Query**: _"If I cut dining by 20% and transport by 15%, when do I hit my emergency fund goal?"_

**What to show**:
1. `scenario_engine` computes exact new surplus: ₹X → ₹Y (show calculation)
2. `monte_carlo` runs 1,000 paths in <50ms → p50: 14 months, p90: 19 months
3. Prompt shows `<ANALYSIS>` block with exact math, not estimates
4. Response cites exact figures from analysis block (SelfRAG verified)

**Talking point**: _"Most AI assistants hallucinate financial numbers. BudgetBandhu separates math from language. The AI only writes sentences — a deterministic engine does all arithmetic."_

---

## Demo Scenario 3: Behavioral Intelligence — "It Knows Your Type"

**Setup**: User's trajectory snapshot shows `impulse_spender_reward_driven` archetype, weekend/weekday ratio of 2.1.

**Query**: _"I spent ₹3,000 on Zomato this weekend. Help."_

**What to show**:
1. Trajectory memory shows archetype + weekend ratio
2. Procedural memory matches `soft_nudge_evening` strategy → gentle tone
3. Response acknowledges first, then redirects (no lecture)
4. Compare: running same query for a `disciplined_saver` → gets analytical response

**Talking point**: _"The same overspend gets a completely different response for different behavioral archetypes. This is personalization at the cognitive level."_

---

## Demo Scenario 4: Safety — "A SEBI-Compliant Financial Advisor"

**Query**: _"Should I invest in crypto to recover my losses fast?"_

**What to show**:
1. Safety guard detects: `crypto` + `fast returns` pattern
2. Soft replacement applied: certainty language removed
3. RBI + SEBI disclaimer automatically injected
4. Flagged for review = False (within safe bounds)

BONUS: Try _"This Bitcoin will definitely 10× in 6 months"_ → show prohibited content filter.

**Talking point**: _"BudgetBandhu is constitutionally safe. It's the only AI financial assistant that explicitly enforces SEBI compliance at the code level — not just through prompting."_

---

## Demo Scenario 5: Full Advisory — "The Financial Operating System"

**Query**: _"Give me a complete review of my financial health"_

**What to show**:
1. All 5 memory tiers activate simultaneously (show `tiers_loaded` in provenance)
2. Budget calculator: 50/30/20 compliance report
3. Anomaly detection: flags ₹4,200 Zomato charge (3.2σ spike)
4. Subscription audit: ₹8,400/year in forgotten subscriptions
5. Goal Monte Carlo: p50 = 16 months, p90 = 22 months
6. FinalResponse provenance: shows exactly which tier sourced which advice

**Talking point**: _"A human financial advisor would charge ₹5,000 for this review. BudgetBandhu does it in 4 seconds, with full audit trail, every time."_

---

## Key Differentiators to Highlight

| Feature | ChatGPT | Generic RAG | BudgetBandhu |
|---------|---------|-------------|--------------|
| Remembers past sessions | ❌ | ❌ | ✅ (5-tier memory) |
| Deterministic math | ❌ | ❌ | ✅ (zero LLM arithmetic) |
| Behavioral archetypes | ❌ | ❌ | ✅ (6 archetypes) |
| Causal reasoning | ❌ | ❌ | ✅ (rule-based counterfactuals) |
| SEBI/RBI compliance | ❌ | ❌ | ✅ (constitutional filter) |
| Hallucination guard | ❌ | ❌ | ✅ (SelfRAG 4-criterion) |
| Goal simulation | ❌ | ❌ | ✅ (Monte Carlo, 1000 paths) |

---

## Fallback if Ollama is Slow

If generation takes >10s, show the **analysis output** directly:
```python
# Quick demo: show deterministic tools without LLM
from tools.financial_toolkit import budget_calculator, detect_anomalies
result = budget_calculator(50000, {"food": 8000, "rent": 12000, "transport": 3000})
print(f"Savings rate: {result.savings_rate:.1%}")
print(f"Surplus: Rs.{result.surplus_deficit:,.0f}")
```

_"Even without the language model, the deterministic financial brain works perfectly."_
