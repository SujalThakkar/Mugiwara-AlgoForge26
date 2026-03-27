import numpy as np
import os
import random
from datetime import datetime, timedelta

random.seed(42)
np.random.seed(42)

CATEGORIES = [
    "Food & Dining", "Transport", "Shopping",
    "Entertainment", "Utilities & Bills", "Groceries"
]
N_USERS    = 2000
N_DAYS     = 180
WINDOW     = 30
FORECAST   = 7

os.makedirs("data", exist_ok=True)


def get_month_day(base_date: datetime, offset_days: int) -> tuple[int, int]:
    d = base_date + timedelta(days=offset_days)
    return d.month, d.day


def generate_user_history(n_days: int = N_DAYS) -> np.ndarray:
    """
    Generates realistic Indian daily spending for one synthetic user.
    Returns ndarray of shape (n_days, 6).
    """
    base = datetime(2024, 1, 1)
    income_mult = random.uniform(0.5, 2.5)   # income tier variation
    spend = np.zeros((n_days, 6), dtype=np.float32)

    # per-user base rates (₹/day)
    base_food        = random.uniform(180, 450)
    base_transport   = random.uniform(60, 250)
    base_entertain   = random.uniform(100, 500)
    base_groceries   = random.uniform(250, 700)

    for day in range(n_days):
        _, dom = get_month_day(base, day)
        dow = day % 7
        is_weekend = dow >= 5

        # ── Food & Dining ──────────────────────────────────────────────
        food_base = base_food * (1.45 if is_weekend else 1.0)
        spend[day, 0] = max(0, np.random.normal(food_base, food_base * 0.25))

        # ── Transport ──────────────────────────────────────────────────
        if is_weekend:
            spend[day, 1] = max(0, np.random.normal(base_transport * 0.4,
                                                     base_transport * 0.2))
        else:
            spend[day, 1] = max(0, np.random.normal(base_transport,
                                                     base_transport * 0.3))

        # ── Shopping (spike 2-3x per month) ────────────────────────────
        if dom in [random.randint(1, 14), random.randint(15, 28)]:
            spend[day, 2] = max(0, np.random.normal(1600, 500))
        elif random.random() < 0.05:           # impulse buy
            spend[day, 2] = max(0, np.random.normal(600, 200))

        # ── Entertainment (weekends only mostly) ───────────────────────
        if is_weekend:
            spend[day, 3] = max(0, np.random.normal(base_entertain,
                                                     base_entertain * 0.35))
        elif random.random() < 0.08:           # weekday treat
            spend[day, 3] = max(0, np.random.normal(200, 80))

        # ── Utilities & Bills (5th-9th of month) ───────────────────────
        if 4 <= dom <= 9:
            spend[day, 4] = max(0, np.random.normal(1100, 280))

        # ── Groceries ──────────────────────────────────────────────────
        if is_weekend:
            spend[day, 5] = max(0, np.random.normal(base_groceries,
                                                     base_groceries * 0.2))
        else:
            spend[day, 5] = max(0, np.random.normal(base_groceries * 0.18,
                                                     50))

    spend *= income_mult
    # add 5% gaussian noise across the board
    noise = np.random.normal(1.0, 0.05, spend.shape)
    return (spend * np.clip(noise, 0.85, 1.15)).astype(np.float32)


print(f"Generating LSTM sequences for {N_USERS} synthetic users...")
X_list, y_list = [], []

for user_i in range(N_USERS):
    history = generate_user_history(N_DAYS)
    # stride-3 sliding window to maximise samples without full overlap
    for start in range(0, N_DAYS - WINDOW - FORECAST, 3):
        X_list.append(history[start:start + WINDOW])
        y_list.append(history[start + WINDOW:start + WINDOW + FORECAST])

X = np.array(X_list, dtype=np.float32)
y = np.array(y_list, dtype=np.float32)

print(f"Total sequences → X: {X.shape}  y: {y.shape}")
np.savez_compressed("data/lstm_training_sequences.npz", X=X, y=y)
print("✅ Saved → data/lstm_training_sequences.npz")