import numpy as np
import pandas as pd
import joblib
import json
import os
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report

MODEL_DIR = "models/isolation_forest"
os.makedirs(MODEL_DIR, exist_ok=True)
np.random.seed(42)

CATEGORIES  = ["Food & Dining", "Transport", "Shopping",
               "Utilities & Bills", "Healthcare", "Entertainment"]
CAT_MEANS   = {"Food & Dining": 280, "Transport": 150, "Shopping": 1200,
               "Utilities & Bills": 800, "Healthcare": 500, "Entertainment": 350}
CAT_STDS    = {k: v * 0.25 for k, v in CAT_MEANS.items()}
MERCHANTS   = {
    "Food & Dining":    ["ZOMATO", "SWIGGY", "McDONALDS", "DOMINOS", "STARBUCKS"],
    "Transport":        ["OLA_CAB", "UBER_INDIA", "IRCTC", "RAPIDO", "REDBUS"],
    "Shopping":         ["AMAZON_IN", "FLIPKART", "MYNTRA", "AJIO", "NYKAA"],
    "Utilities & Bills":["JIO_RCHG", "AIRTEL", "BESCOM", "TATA_PWR", "BWSSB"],
    "Healthcare":       ["APOLLO_PHR", "1MG", "PRACTO", "NETMEDS", "MEDPLUS"],
    "Entertainment":    ["NETFLIX", "SPOTIFY", "BOOKMYSHOW", "PVR", "HOTSTAR"],
}


def make_normal_transactions(n: int = 300) -> list[dict]:
    base = datetime(2024, 1, 1, 10, 0, 0)
    rows = []
    for i in range(n):
        dt  = base + timedelta(hours=i * 5 + np.random.randint(0, 4))
        cat = np.random.choice(CATEGORIES,
                               p=[0.35, 0.25, 0.15, 0.10, 0.08, 0.07])
        merchant = np.random.choice(MERCHANTS[cat])
        amount   = max(10, np.random.normal(CAT_MEANS[cat], CAT_STDS[cat]))
        rows.append({
            "id": f"txn_{i:04d}", "datetime": dt, "category": cat,
            "amount": round(amount, 2), "merchant": merchant,
            "is_anomaly": 0, "anomaly_type": None
        })
    return rows


def inject_anomalies(rows: list[dict]) -> list[dict]:
    n      = len(rows)
    used   = set()
    result = rows.copy()

    def pick(exclude=None):
        while True:
            idx = np.random.randint(50, n)
            if idx not in used and idx != exclude:
                used.add(idx)
                return idx

    # SPIKE — amount 5-10x normal
    for _ in range(12):
        idx = pick()
        result[idx]["amount"] = round(
            CAT_MEANS[result[idx]["category"]] * np.random.uniform(5, 10), 2)
        result[idx]["is_anomaly"] = 1
        result[idx]["anomaly_type"] = "SPIKE"

    # DUPLICATE — same merchant same amount within 24h
    for _ in range(8):
        idx  = pick()
        idx2 = pick(idx)
        result[idx2]["merchant"] = result[idx]["merchant"]
        result[idx2]["amount"]   = result[idx]["amount"]
        result[idx2]["datetime"] = result[idx]["datetime"] + timedelta(hours=2)
        result[idx2]["is_anomaly"] = 1
        result[idx2]["anomaly_type"] = "DUPLICATE"

    # OFF_HOURS — 1AM-4AM
    for _ in range(8):
        idx = pick()
        result[idx]["datetime"] = result[idx]["datetime"].replace(
            hour=np.random.randint(1, 5))
        result[idx]["amount"] = round(
            CAT_MEANS[result[idx]["category"]] * np.random.uniform(3, 7), 2)
        result[idx]["is_anomaly"] = 1
        result[idx]["anomaly_type"] = "OFF_HOURS"

    # NEW_MERCHANT high-value
    for _ in range(6):
        idx = pick()
        result[idx]["merchant"] = f"UNKNOWN_MERCH_{np.random.randint(1000,9999)}"
        result[idx]["amount"]   = round(np.random.uniform(3000, 8000), 2)
        result[idx]["is_anomaly"] = 1
        result[idx]["anomaly_type"] = "NEW_MERCHANT"

    return result


def engineer_features(df: pd.DataFrame) -> np.ndarray:
    """
    6 features per transaction:
      0  amount_normalized  (amount / category mean)
      1  hour_of_day
      2  day_of_week
      3  amount_zscore      (vs category)
      4  days_since_same_merchant (capped at 30)
      5  amount_vs_median_ratio
    """
    cat_means   = df.groupby("category")["amount"].mean().to_dict()
    cat_stds    = df.groupby("category")["amount"].std().fillna(1).to_dict()
    cat_medians = df.groupby("category")["amount"].median().to_dict()

    last_merchant_day = {}
    features = []

    for _, row in df.iterrows():
        mean   = cat_means.get(row["category"], row["amount"])
        std    = max(cat_stds.get(row["category"], 1.0), 1.0)
        median = cat_medians.get(row["category"], row["amount"])
        hour   = row["datetime"].hour
        dow    = row["datetime"].weekday()

        amt_norm   = row["amount"] / (mean + 1e-9)
        zscore     = (row["amount"] - mean) / std
        amt_median = row["amount"] / (median + 1e-9)

        key = (row["merchant"], row["category"])
        today = row["datetime"].toordinal()
        if key in last_merchant_day:
            days_since = min(30, today - last_merchant_day[key])
        else:
            days_since = 30.0
        last_merchant_day[key] = today

        features.append([amt_norm, hour, dow, zscore, days_since, amt_median])

    return np.array(features, dtype=np.float32)


print("Generating synthetic transaction dataset...")
normal_txns   = make_normal_transactions(300)
all_txns      = inject_anomalies(normal_txns)
df            = pd.DataFrame(all_txns).sort_values("datetime").reset_index(drop=True)
labels        = df["is_anomaly"].values
anomaly_types = df["anomaly_type"].values

print(f"Total transactions : {len(df)}")
print(f"Normal             : {(labels == 0).sum()}")
print(f"Anomalies injected : {(labels == 1).sum()}")
for atype in ["SPIKE", "DUPLICATE", "OFF_HOURS", "NEW_MERCHANT"]:
    print(f"  {atype}: {(anomaly_types == atype).sum()}")

X = engineer_features(df)
scaler   = StandardScaler()
X_scaled = scaler.fit_transform(X)

print("\nTraining IsolationForest...")
model = IsolationForest(
    n_estimators=200,
    contamination=0.10,
    max_samples="auto",
    random_state=42,
    n_jobs=-1
)
model.fit(X_scaled)

preds    = model.predict(X_scaled)           # -1=anomaly, +1=normal
detected = (preds == -1).astype(int)
true_an  = labels

print("\nDetection Report:")
print(classification_report(true_an, detected,
                             target_names=["Normal", "Anomaly"]))

tp = ((detected == 1) & (true_an == 1)).sum()
print(f"True positives: {tp} / {true_an.sum()} injected anomalies detected")

joblib.dump(model,  f"{MODEL_DIR}/model.joblib")
joblib.dump(scaler, f"{MODEL_DIR}/scaler.joblib")

cat_stats = {
    cat: {
        "mean":   round(float(df[df["category"] == cat]["amount"].mean()), 2),
        "std":    round(float(df[df["category"] == cat]["amount"].std()), 2),
        "median": round(float(df[df["category"] == cat]["amount"].median()), 2),
    }
    for cat in CATEGORIES
}
with open(f"{MODEL_DIR}/category_stats.json", "w") as f:
    json.dump(cat_stats, f, indent=2)
with open(f"{MODEL_DIR}/metadata.json", "w") as f:
    json.dump({
        "trained_at":      datetime.utcnow().isoformat(),
        "n_estimators":    200,
        "contamination":   0.10,
        "n_train_samples": len(df),
        "n_features":      6,
        "feature_names":   ["amount_normalized", "hour_of_day", "day_of_week",
                            "amount_zscore", "days_since_same_merchant",
                            "amount_vs_median_ratio"],
        "categories":      CATEGORIES,
    }, f, indent=2)

print(f"\n✅ IsolationForest saved → {MODEL_DIR}/")