import numpy as np
import joblib
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime

MODEL_DIR = "models/q_learning"
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs("docs", exist_ok=True)
np.random.seed(42)

# ── State & Action Definitions ─────────────────────────────────────────────
INCOME_BRACKETS  = 4    # 0-15k | 15-30k | 30-50k | 50k+
SAVINGS_BUCKETS  = 4    # poor<5% | ok 5-15% | good 15-30% | great>30%
GOAL_PROGRESS    = 3    # behind | on_track | ahead
OVERSPEND_CATS   = 5    # food | transport | entertainment | shopping | other
N_STATES  = INCOME_BRACKETS * SAVINGS_BUCKETS * GOAL_PROGRESS * OVERSPEND_CATS
N_ACTIONS = 12

ACTIONS = [
    "increase_food_budget",          # 0
    "decrease_food_budget",          # 1
    "increase_transport_budget",     # 2
    "decrease_transport_budget",     # 3
    "increase_entertainment_budget", # 4
    "decrease_entertainment_budget", # 5
    "increase_shopping_budget",      # 6
    "decrease_shopping_budget",      # 7
    "increase_savings_target",       # 8
    "decrease_savings_target",       # 9
    "increase_emergency_fund",       # 10
    "maintain_current",              # 11
]

ACTION_DESCRIPTIONS = {
    0:  "Increase food budget by 10% — your actual spend consistently exceeds limit.",
    1:  "Reduce food budget by 10% — redirecting surplus to savings.",
    2:  "Increase transport budget — commute costs are underestimated.",
    3:  "Reduce transport budget — you're spending less than allocated.",
    4:  "Increase entertainment — current limit is too restrictive.",
    5:  "Cut entertainment by 10% — accelerates goal progress.",
    6:  "Increase shopping budget — reflects realistic spending.",
    7:  "Reduce shopping budget — top overspend category this month.",
    8:  "Raise savings target — your income supports a higher rate.",
    9:  "Lower savings target — current target is unsustainable.",
    10: "Boost emergency fund contribution — below 3-month threshold.",
    11: "Maintain current allocations — budget is well balanced.",
}


def encode_state(ib: int, sb: int, gp: int, oc: int) -> int:
    return ib * (SAVINGS_BUCKETS * GOAL_PROGRESS * OVERSPEND_CATS) + \
           sb * (GOAL_PROGRESS * OVERSPEND_CATS) + \
           gp * OVERSPEND_CATS + oc


def decode_state(s: int) -> tuple[int, int, int, int]:
    oc = s % OVERSPEND_CATS;          s //= OVERSPEND_CATS
    gp = s % GOAL_PROGRESS;           s //= GOAL_PROGRESS
    sb = s % SAVINGS_BUCKETS;         ib = s // SAVINGS_BUCKETS
    return ib, sb, gp, oc


class FinancialEnvironment:
    """
    Simulates a month in a user's financial life.
    State = (income_bracket, savings_bucket, goal_progress, overspend_cat)
    """

    def __init__(self):
        self.state = None
        self.reset()

    def reset(self) -> int:
        ib = np.random.randint(0, INCOME_BRACKETS)
        sb = np.random.randint(0, SAVINGS_BUCKETS)
        gp = np.random.randint(0, GOAL_PROGRESS)
        oc = np.random.randint(0, OVERSPEND_CATS)
        self.state = (ib, sb, gp, oc)
        return encode_state(*self.state)

    def step(self, action: int) -> tuple[int, float, bool]:
        ib, sb, gp, oc = self.state
        reward = 0.0
        new_sb, new_gp = sb, gp

        # ── Reward logic ──────────────────────────────────────────────
        # decrease the category that IS the overspend
        decrease_map = {0: 1, 1: 3, 2: 5, 3: 7}   # oc → decrease action
        increase_map = {0: 0, 1: 2, 2: 4, 3: 6}

        if action == decrease_map.get(oc, -1):
            if np.random.random() < 0.72:
                new_sb = min(3, sb + 1)
                reward += 10.0
                if new_sb > sb:
                    new_gp = min(2, gp + 1)
                    reward += 5.0
            else:
                reward -= 1.0

        elif action == 8:                 # increase savings target
            if sb <= 1:
                new_sb = min(3, sb + 1)
                reward += 10.0
                new_gp = min(2, gp + 1)
                reward += 3.0
            else:
                reward += 2.0

        elif action == 10:                # emergency fund
            reward += 4.0 if sb >= 1 else 1.0

        elif action == 11:                # maintain
            if sb >= 2 and gp >= 1:
                reward += 5.0
            elif sb >= 3:
                reward += 3.0
            else:
                reward -= 1.0

        elif action == increase_map.get(oc, -1):
            # increasing the overspend category → bad
            reward -= 4.0

        elif action in [0, 2, 4, 6] and sb <= 1:
            reward -= 3.0   # increasing budgets when savings poor

        elif action == 9 and sb <= 1:
            reward -= 8.0   # lowering savings when already poor

        else:
            reward += np.random.uniform(-1.5, 2.5)

        # penalise staying in bad states
        if sb == 0:
            reward -= 2.0
        if gp == 0:
            reward -= 1.5

        # bonus for reaching good state
        if new_sb == 3 and new_gp == 2:
            reward += 8.0

        # stochastic income shift
        new_ib = int(np.clip(ib + np.random.choice([-1, 0, 0, 0, 1]), 0, 3))
        new_oc = np.random.randint(0, OVERSPEND_CATS)

        self.state = (new_ib, new_sb, new_gp, new_oc)
        return encode_state(*self.state), round(reward, 3), False


# ── Q-Learning Training ────────────────────────────────────────────────────
Q           = np.zeros((N_STATES, N_ACTIONS), dtype=np.float64)
alpha       = 0.12
gamma       = 0.95
epsilon     = 1.0
epsilon_min = 0.05
N_EPISODES  = 12000
STEPS_PER   = 12          # 12 months per episode
decay       = (epsilon - epsilon_min) / (N_EPISODES * 0.8)

env             = FinancialEnvironment()
rewards_history = []
visit_counts    = np.zeros(N_STATES, dtype=np.int32)

print(f"Training Q-Learning agent ({N_EPISODES} episodes × {STEPS_PER} steps)...")
for ep in range(N_EPISODES):
    state     = env.reset()
    ep_reward = 0.0

    for _ in range(STEPS_PER):
        visit_counts[state] += 1
        if np.random.random() < epsilon:
            action = np.random.randint(0, N_ACTIONS)
        else:
            action = int(np.argmax(Q[state]))

        next_state, reward, _ = env.step(action)
        # Q-update
        Q[state, action] += alpha * (
            reward + gamma * np.max(Q[next_state]) - Q[state, action]
        )
        state      = next_state
        ep_reward += reward

    rewards_history.append(ep_reward)
    epsilon = max(epsilon_min, epsilon - decay)

    if (ep + 1) % 2000 == 0:
        avg = np.mean(rewards_history[-500:])
        print(f"  Episode {ep+1:5d} | Avg reward (500): {avg:+.2f} "
              f"| ε: {epsilon:.4f}")

# ── Save artefacts ─────────────────────────────────────────────────────────
np.save(f"{MODEL_DIR}/q_table.npy", Q)
np.save(f"{MODEL_DIR}/visit_counts.npy", visit_counts)

encoder = {
    "n_states":          N_STATES,
    "n_actions":         N_ACTIONS,
    "income_thresholds": [15000, 30000, 50000],
    "savings_thresholds":[0.05, 0.15, 0.30],
    "goal_thresholds":   [0.33, 0.66],
    "overspend_categories": [
        "Food & Dining", "Transport", "Entertainment", "Shopping", "Other"
    ],
    "actions":           ACTIONS,
    "action_descriptions": ACTION_DESCRIPTIONS,
}
joblib.dump(encoder, f"{MODEL_DIR}/state_encoder.joblib")
with open(f"{MODEL_DIR}/training_metadata.json", "w") as f:
    json.dump({
        "trained_at":       datetime.utcnow().isoformat(),
        "n_episodes":       N_EPISODES,
        "steps_per_episode":STEPS_PER,
        "alpha":            alpha,
        "gamma":            gamma,
        "final_epsilon":    round(epsilon, 4),
        "avg_reward_last500": round(float(np.mean(rewards_history[-500:])), 3),
        "n_states":         N_STATES,
        "n_actions":        N_ACTIONS,
    }, f, indent=2)

# ── Reward curve plot ──────────────────────────────────────────────────────
window   = 300
smoothed = np.convolve(rewards_history,
                       np.ones(window) / window, mode="valid")
plt.figure(figsize=(12, 4))
plt.plot(smoothed, color="#2563EB", linewidth=1.5, label="Smoothed reward")
plt.axhline(y=np.mean(rewards_history[-2000:]),
            color="#16A34A", linestyle="--", linewidth=1.2,
            label=f"Final avg: {np.mean(rewards_history[-2000:]):.1f}")
plt.title("Q-Learning Training Reward Curve (BudgetBandhu)", fontsize=13)
plt.xlabel("Episode")
plt.ylabel("Episode Reward")
plt.legend()
plt.tight_layout()
plt.savefig("docs/q_learning_reward_curve.png", dpi=150)
print("Reward curve → docs/q_learning_reward_curve.png")

# ── Sample recommendations ─────────────────────────────────────────────────
print("\nTop 6 state → optimal action examples:")
samples = [
    (encode_state(1, 0, 0, 0), "₹15-30k income | poor savings | behind | food overspend"),
    (encode_state(2, 1, 1, 3), "₹30-50k income | ok savings  | on track | shopping overspend"),
    (encode_state(3, 3, 2, 4), "₹50k+ income   | great savings | ahead | other"),
    (encode_state(0, 0, 0, 2), "₹0-15k income  | poor savings | behind | entertain overspend"),
    (encode_state(1, 2, 1, 1), "₹15-30k income | good savings | on track | transport overspend"),
    (encode_state(2, 2, 2, 4), "₹30-50k income | good savings | ahead | other"),
]
for s, desc in samples:
    best = int(np.argmax(Q[s]))
    conf = float(np.max(Q[s]))
    print(f"  {desc}\n    → [{best}] {ACTIONS[best]}  (Q={conf:.2f})\n")

print(f"✅ Q-table saved → {MODEL_DIR}/")