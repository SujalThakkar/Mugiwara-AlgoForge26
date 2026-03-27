import os
import json
import joblib
import numpy as np

MODEL_DIR = "models/q_learning"

ACTIONS = [
    "increase_food_budget",
    "decrease_food_budget",
    "increase_transport_budget",
    "decrease_transport_budget",
    "increase_entertainment_budget",
    "decrease_entertainment_budget",
    "increase_shopping_budget",
    "decrease_shopping_budget",
    "increase_savings_target",
    "decrease_savings_target",
    "increase_emergency_fund",
    "maintain_current",
]

ACTION_REASONING = {
    "increase_food_budget":          "Food spend consistently exceeds budget. Realistic target set to reduce stress.",
    "decrease_food_budget":          "Reducing food budget by 10% frees ₹{freed}/month for savings goals.",
    "increase_transport_budget":     "Commute costs are underestimated. Adjusted to reflect actual spend.",
    "decrease_transport_budget":     "Transport spend is below budget. Reallocating surplus to savings.",
    "increase_entertainment_budget": "Current entertainment limit is too restrictive. Small increase for wellbeing.",
    "decrease_entertainment_budget": "Cutting entertainment by 10% accelerates your goal by ~{months} months.",
    "increase_shopping_budget":      "Shopping budget is consistently underestimated. Adjusted for accuracy.",
    "decrease_shopping_budget":      "Shopping is your top overspend category. Cutting allocation to realign.",
    "increase_savings_target":       "Your income supports a higher savings rate. Raising target by 5%.",
    "decrease_savings_target":       "Current savings target is unsustainable. Reducing to realistic level.",
    "increase_emergency_fund":       "Emergency fund is below 3-month threshold. Prioritising buffer.",
    "maintain_current":              "Budget is well-balanced. No changes recommended this month.",
}

OVERSPEND_CAT_MAP = {
    "Food & Dining":  0,
    "Transport":      1,
    "Entertainment":  2,
    "Shopping":       3,
}

DEFAULT_ALLOCATION_RATIOS = {
    "Food & Dining":      0.25,
    "Transport":          0.10,
    "Entertainment":      0.05,
    "Shopping":           0.10,
    "Utilities & Bills":  0.10,
    "Groceries":          0.10,
    "Healthcare":         0.05,
    "Education":          0.05,
    "Savings":            0.20,
}


class UserFinancialState:
    def __init__(self, monthly_income: float, current_savings_rate: float,
                 goal_progress: float = 0.0,
                 category_spend: dict | None = None,
                 budget_allocations: dict | None = None):
        self.monthly_income       = monthly_income
        self.current_savings_rate = current_savings_rate
        self.goal_progress        = goal_progress
        self.category_spend       = category_spend       or {}
        self.budget_allocations   = budget_allocations   or {}


class BudgetRecommendation:
    def __init__(self, action_id: int, action_name: str,
                 new_allocations: dict, reasoning: str,
                 expected_savings_improvement: float, confidence: float):
        self.action_id                    = action_id
        self.action_name                  = action_name
        self.new_allocations              = new_allocations
        self.reasoning                    = reasoning
        self.expected_savings_improvement = round(expected_savings_improvement, 4)
        self.confidence                   = round(confidence, 4)

    def dict(self) -> dict:
        return self.__dict__

    def __repr__(self):
        return (f"BudgetRecommendation(action={self.action_name!r}, "
                f"confidence={self.confidence:.2f})")


class BudgetPolicyLearner:
    """
    Recommends adaptive monthly budget adjustments using a trained Q-table.

    State space  : 240 (4 income × 4 savings × 3 goal × 5 overspend)
    Action space : 12 budget actions
    Falls back to rule-based logic if Q-table not found.

    Example:
        learner = BudgetPolicyLearner()
        state   = UserFinancialState(monthly_income=25000,
                                     current_savings_rate=0.03,
                                     category_spend={"Food & Dining": 8500})
        rec = learner.get_recommendation(state)
        # BudgetRecommendation(action='decrease_food_budget', confidence=0.81)
    """

    def __init__(self, model_dir: str = MODEL_DIR):
        self._model_dir = model_dir
        self._q_table   = None
        self._encoder   = None
        self._loaded    = False
        self._load()

    # ── Initialisation ────────────────────────────────────────────────
    def _load(self):
        q_path   = os.path.join(self._model_dir, "q_table.npy")
        enc_path = os.path.join(self._model_dir, "state_encoder.joblib")

        if not (os.path.exists(q_path) and os.path.exists(enc_path)):
            print("[PolicyLearner] ⚠ Q-table not found — using rule-based fallback.")
            return
        try:
            self._q_table = np.load(q_path)
            self._encoder = joblib.load(enc_path)
            self._loaded  = True
            print(f"[PolicyLearner] ✅ Q-table loaded "
                  f"(shape={self._q_table.shape}).")
        except Exception as e:
            print(f"[PolicyLearner] ⚠ Load error: {e}")

    def is_loaded(self) -> bool:
        return self._loaded

    # ── Public API ────────────────────────────────────────────────────
    def get_recommendation(self,
                           state: UserFinancialState) -> BudgetRecommendation:
        """
        Return the optimal budget action for the given financial state.

        Args:
            state: UserFinancialState
        Returns:
            BudgetRecommendation
        """
        if self._loaded:
            try:
                state_idx = self._encode_state(state)
                q_vals    = self._q_table[state_idx]
                action_id = int(np.argmax(q_vals))
                raw_conf  = float(q_vals[action_id])
                # normalise Q-value to [0, 1]
                q_range   = q_vals.max() - q_vals.min()
                conf = float(
                    (raw_conf - q_vals.min()) / (q_range + 1e-9)
                ) if q_range > 0 else 0.5
                conf = round(min(max(conf, 0.30), 0.99), 4)
            except Exception as e:
                print(f"[PolicyLearner] encode/lookup error: {e}")
                action_id = self._rule_action(state)
                conf = 0.50
        else:
            action_id = self._rule_action(state)
            conf = 0.50

        action_name  = ACTIONS[action_id]
        new_allocs   = self._apply_action(action_id, state)
        reasoning    = self._build_reasoning(action_name, state, new_allocs)
        saving_delta = 0.03 if "savings" in action_name or "decrease" in action_name \
                       else 0.01

        return BudgetRecommendation(
            action_id=action_id,
            action_name=action_name,
            new_allocations=new_allocs,
            reasoning=reasoning,
            expected_savings_improvement=saving_delta,
            confidence=conf,
        )

    def update_from_feedback(self, state: UserFinancialState,
                              action_taken: int, reward: float,
                              next_state: UserFinancialState) -> None:
        """Online Q-table update from real user outcome."""
        if not self._loaded:
            return
        try:
            si = self._encode_state(state)
            ni = self._encode_state(next_state)
            old = self._q_table[si, action_taken]
            self._q_table[si, action_taken] = (
                old + 0.10 * (reward + 0.95 * np.max(self._q_table[ni]) - old)
            )
        except Exception as e:
            print(f"[PolicyLearner] feedback update error: {e}")

    # ── State encoding ────────────────────────────────────────────────
    def _encode_state(self, state: UserFinancialState) -> int:
        income = state.monthly_income
        if   income < 15_000: ib = 0
        elif income < 30_000: ib = 1
        elif income < 50_000: ib = 2
        else:                  ib = 3

        sr = state.current_savings_rate
        if   sr < 0.05: sb = 0
        elif sr < 0.15: sb = 1
        elif sr < 0.30: sb = 2
        else:            sb = 3

        gp = state.goal_progress
        if   gp < 0.33: gpi = 0
        elif gp < 0.66: gpi = 1
        else:            gpi = 2

        # top overspend category (ratio of spend to budget)
        max_ratio, top_oc = 0.0, 4   # default: Other
        for cat, cidx in OVERSPEND_CAT_MAP.items():
            budget = state.budget_allocations.get(cat,
                         state.monthly_income * DEFAULT_ALLOCATION_RATIOS.get(cat, 0.10))
            spend  = state.category_spend.get(cat, 0.0)
            ratio  = spend / (budget + 1e-9)
            if ratio > max_ratio:
                max_ratio = ratio
                top_oc    = cidx

        return ib * (4 * 3 * 5) + sb * (3 * 5) + gpi * 5 + top_oc

    # ── Action application ────────────────────────────────────────────
    def _apply_action(self, action_id: int,
                       state: UserFinancialState) -> dict[str, float]:
        income = state.monthly_income
        allocs = {
            cat: state.budget_allocations.get(cat, round(income * ratio, 2))
            for cat, ratio in DEFAULT_ALLOCATION_RATIOS.items()
        }
        action = ACTIONS[action_id]
        delta  = 0.10   # 10% adjustment

        cat_key = None
        if "food"          in action: cat_key = "Food & Dining"
        elif "transport"   in action: cat_key = "Transport"
        elif "entertainment"in action:cat_key = "Entertainment"
        elif "shopping"    in action: cat_key = "Shopping"
        elif "savings"     in action: cat_key = "Savings"
        elif "emergency"   in action: cat_key = "Savings"

        if cat_key:
            current = allocs.get(cat_key, 0.0)
            if "increase" in action:
                allocs[cat_key]  = round(current * (1 + delta), 2)
            elif "decrease" in action:
                freed            = current * delta
                allocs[cat_key]  = round(current * (1 - delta), 2)
                allocs["Savings"]= round(allocs.get("Savings", 0.0) + freed, 2)

        return allocs

    def _build_reasoning(self, action_name: str,
                          state: UserFinancialState,
                          new_allocs: dict) -> str:
        template = ACTION_REASONING.get(action_name, "Optimising your budget.")
        cat_key  = None
        if "food"           in action_name: cat_key = "Food & Dining"
        elif "transport"    in action_name: cat_key = "Transport"
        elif "entertainment"in action_name: cat_key = "Entertainment"
        elif "shopping"     in action_name: cat_key = "Shopping"

        if cat_key:
            spend    = state.category_spend.get(cat_key, 0.0)
            old_bud  = state.budget_allocations.get(
                cat_key,
                state.monthly_income * DEFAULT_ALLOCATION_RATIOS.get(cat_key, 0.10)
            )
            new_bud  = new_allocs.get(cat_key, old_bud)
            freed    = abs(old_bud - new_bud)
            months   = round(freed * 12 / (state.monthly_income + 1e-9), 1)
            template = template.replace("{freed}",  f"{freed:,.0f}")
            template = template.replace("{months}", str(months))
            if spend > 0:
                template += (f" Current spend: ₹{spend:,.0f} | "
                             f"New budget: ₹{new_bud:,.0f}.")
        return template

    # ── Rule-based fallback ───────────────────────────────────────────
    def _rule_action(self, state: UserFinancialState) -> int:
        if state.current_savings_rate < 0.05:
            return 8   # increase_savings_target

        for cat, action_id in [("Food & Dining",  1),
                                ("Transport",      3),
                                ("Entertainment",  5),
                                ("Shopping",       7)]:
            budget = state.budget_allocations.get(
                cat, state.monthly_income * DEFAULT_ALLOCATION_RATIOS.get(cat, 0.10)
            )
            spend  = state.category_spend.get(cat, 0.0)
            if spend > budget * 1.20:
                return action_id

        if state.current_savings_rate >= 0.25 and state.goal_progress >= 0.66:
            return 11   # maintain

        return 8   # default to increasing savings