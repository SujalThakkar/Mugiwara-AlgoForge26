"""
intelligence/ml_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Orchestrates all 4 ML models for a complete CSV processing job.

Pipeline
--------
    1. Parse + normalise CSV
    2. Categorise all transactions (GPU-batched)
    3. Detect anomalies (IsolationForest + rules)
    4. Build daily spend matrix for LSTM
    5. Forecast next 7 days + 30-day projection
    6. Build UserFinancialState
    7. Get Q-Learning budget recommendation
    8. Assemble & return MLPipelineResult dict

Example
-------
    pipeline = BudgetBandhuMLPipeline()
    result   = await pipeline.process_csv(csv_bytes, "user_123")
"""

from __future__ import annotations

import asyncio
import io
import statistics
import time
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

from intelligence.anomaly_detector import AnomalyDetector
from intelligence.categorizer      import TransactionCategorizer
from intelligence.forecaster       import SpendingForecaster
from intelligence.policy_learner   import BudgetPolicyLearner, UserFinancialState

# ── Transaction type helpers ──────────────────────────────────────────────────

CREDIT_KEYWORDS: frozenset[str] = frozenset({
    "credit", "cr", "received", "refund", "cashback",
    "inward", "reversal", "salary", "interest",
})


def _is_debit(txn_type: str) -> bool:
    return str(txn_type).lower().strip() not in CREDIT_KEYWORDS


# ── Income estimator ──────────────────────────────────────────────────────────

def _estimate_monthly_income(
    credit_txns: list[dict],
    debit_total: float,
    df: pd.DataFrame,
) -> float:
    """
    FIX #4 — Compute monthly income from actual calendar months.

    Old (broken): total_income / (row_count / 30)
        → len(df)=576 → n_days=19.2 → ₹7 813 instead of ₹50 000.

    New (correct):
        1. Sum credits per calendar month (MM-YYYY key).
        2. Take the *median* of monthly totals — robust to months with
           irregular large transfers.
        3. Fall back to debit-based estimate if no credit data.
    """
    # --- Monthly credit aggregation ----------------------------------------
    monthly_credits: dict[str, float] = defaultdict(float)
    for txn in credit_txns:
        raw_date = str(txn.get("date", "")).strip()
        # Extract "MM-YYYY" from "DD-MM-YYYY"
        if len(raw_date) >= 10:
            month_key = raw_date[3:10]       # e.g. "01-2024"
        else:
            month_key = "unknown"
        monthly_credits[month_key] += float(txn.get("amount", 0))

    # Remove the "unknown" bucket — unreliable
    monthly_credits.pop("unknown", None)

    if monthly_credits:
        # Median is more robust than mean (avoids one-off large transfers
        # skewing the estimate up, and zero-credit months skewing it down).
        return round(statistics.median(monthly_credits.values()), 2)

    # --- Fallback: infer income from actual date span ----------------------
    try:
        dates = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce").dropna()
        if not dates.empty:
            span_days = max(1, (dates.max() - dates.min()).days + 1)
            span_months = max(1.0, span_days / 30.0)
            return round(debit_total * 1.25 / span_months, 2)
    except Exception:
        pass

    return round(debit_total * 1.25, 2)


# ── Pipeline ──────────────────────────────────────────────────────────────────

class BudgetBandhuMLPipeline:
    """
    Orchestrates all 4 ML models for a complete CSV processing job.

    All 4 bugs fixed:
        #1  Duplicate false positives — handled in AnomalyDetector (24 h window
            + recurring merchant whitelist).
        #2  Credit transactions flagged as SPIKE — handled in AnomalyDetector
            (credits skipped at the top of detect()).
        #3  VELOCITY false alarm on timestamp-less CSVs — handled in
            AnomalyDetector (_has_time_column guard).
        #4  Monthly income wildly underestimated — fixed here via
            per-calendar-month median, not row-count arithmetic.
    """

    def __init__(self) -> None:
        self.categorizer      = TransactionCategorizer()
        self.anomaly_detector = AnomalyDetector()
        self.forecaster       = SpendingForecaster()
        self.policy_learner   = BudgetPolicyLearner()

    # ── Main entry point ───────────────────────────────────────────────

    async def process_csv(self, csv_bytes: bytes, user_id: str) -> dict:
        t0 = time.time()

        # 1. Parse & normalise.
        df = self._parse_csv(csv_bytes)
        if df is None or df.empty:
            return {"error": "Could not parse CSV or no valid rows.", "user_id": user_id}

        txn_list = df.to_dict(orient="records")

        # 2. Categorise (GPU-batched — fastest step).
        descriptions = [str(t.get("description", "")) for t in txn_list]
        cat_results  = self.categorizer.categorize_batch(descriptions)
        for txn, cr in zip(txn_list, cat_results):
            txn["category"] = cr.category

        # 3. Anomaly detection (CPU: rule + IsolationForest).
        #    Credits are already skipped inside AnomalyDetector.detect().
        anomalies      = self.anomaly_detector.detect_batch(txn_list, txn_list)
        flagged        = [a for a in anomalies if a.is_anomaly]
        high_sev_count = sum(1 for a in flagged if a.severity == "HIGH")

        # 4. Build daily spend (debits only).
        daily_spend = self._build_daily_spend(txn_list)

        # 5. Forecast (Torch forward pass — run in thread executor).
        loop     = asyncio.get_event_loop()
        forecast = await loop.run_in_executor(
            None, self.forecaster.forecast, daily_spend, 7
        )

        # 6. Aggregate spend / income.
        debit_txns  = [t for t in txn_list if _is_debit(t.get("transaction_type", "Debit"))]
        credit_txns = [t for t in txn_list if not _is_debit(t.get("transaction_type", "Debit"))]

        total_spend  = sum(t.get("amount", 0) for t in debit_txns)
        total_income = sum(t.get("amount", 0) for t in credit_txns)

        # ── FIX #4 — real monthly income estimate ────────────────────────
        monthly_income = _estimate_monthly_income(credit_txns, total_spend, df)

        # Fall back gracefully if no credit data at all.
        if total_income == 0:
            total_income = total_spend * 1.25

        net_savings  = total_income - total_spend
        savings_rate = net_savings / (total_income + 1e-9)

        cat_breakdown: dict[str, float] = defaultdict(float)
        for t in debit_txns:
            cat_breakdown[t["category"]] += float(t.get("amount", 0))
        cat_breakdown = dict(sorted(
            {k: round(v, 2) for k, v in cat_breakdown.items()}.items(),
            key=lambda kv: kv[1], reverse=True,
        ))

        # 7. Budget recommendation.
        try:
            _dates     = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce").dropna()
            _span_days = max(1, (_dates.max() - _dates.min()).days + 1)
        except Exception:
            _span_days = 30
        n_months = max(1.0, _span_days / 30.0)

        user_state = UserFinancialState(
            monthly_income       = monthly_income,
            current_savings_rate = max(0.0, savings_rate),
            goal_progress        = 0.3,
            category_spend       = {k: round(v / n_months, 2) for k, v in cat_breakdown.items()},
            budget_allocations   = {k: round(monthly_income * 0.12, 2) for k in cat_breakdown},
        )
        budget_rec = self.policy_learner.get_recommendation(user_state)

        # Update forecast savings projection.
        monthly_spend_proj             = forecast.total_predicted_30d
        forecast.savings_projected_30d = round(
            max(0.0, monthly_income - monthly_spend_proj), 2
        )

        processing_ms = int((time.time() - t0) * 1_000)

        return {
            "user_id":                  user_id,
            "transactions_parsed":      len(df),
            "transactions_categorized": [
                {"transaction": txn, "category_result": cr.dict()}
                for txn, cr in zip(txn_list, cat_results)
            ],
            "anomalies_detected":       [a.dict() for a in anomalies],
            "high_severity_anomalies":  high_sev_count,
            "anomaly_summary": {
                "SPIKE":        sum(1 for a in flagged if a.anomaly_type == "SPIKE"),
                "DUPLICATE":    sum(1 for a in flagged if a.anomaly_type == "DUPLICATE"),
                "OFF_HOURS":    sum(1 for a in flagged if a.anomaly_type == "OFF_HOURS"),
                "NEW_MERCHANT": sum(1 for a in flagged if a.anomaly_type == "NEW_MERCHANT"),
                "VELOCITY":     sum(1 for a in flagged if a.anomaly_type == "VELOCITY"),
            },
            "forecast_7d":              forecast.dict(),
            "budget_recommendation":    budget_rec.dict(),
            "category_breakdown":       cat_breakdown,
            "total_spend":              round(total_spend,  2),
            "total_income":             round(total_income, 2),
            "net_savings":              round(net_savings,  2),
            "savings_rate":             round(savings_rate, 4),
            "monthly_income_est":       monthly_income,
            "processing_time_ms":       processing_ms,
            "models_used":              self._active_models(),
        }

    # ── CSV parsing ────────────────────────────────────────────────────

    def _parse_csv(self, csv_bytes: bytes) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_csv(io.BytesIO(csv_bytes))
        except Exception as exc:
            print(f"[Pipeline] CSV parse error: {exc}")
            return None

        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Fuzzy column mapping.
        col_map: dict[str, str] = {}
        for col in df.columns:
            lc = col.lower()
            if   "date"    in lc and "date"             not in col_map.values():
                col_map[col] = "date"
            elif any(x in lc for x in ("desc", "narr", "particular", "detail")) \
                    and "description" not in col_map.values():
                col_map[col] = "description"
            elif any(x in lc for x in ("amount", "debit", "dr")) \
                    and "amount" not in col_map.values():
                col_map[col] = "amount"
            elif any(x in lc for x in ("type", "cr_dr", "mode")) \
                    and "transaction_type" not in col_map.values():
                col_map[col] = "transaction_type"
            elif "balance" in lc and "balance" not in col_map.values():
                col_map[col] = "balance"
            elif "time" in lc and "time" not in col_map.values():
                col_map[col] = "time"     # preserve time column when present
        df = df.rename(columns=col_map)

        # Fallbacks for mandatory columns.
        if "description" not in df.columns:
            text_cols = [c for c in df.columns if df[c].dtype == object]
            if text_cols:
                df = df.rename(columns={text_cols[0]: "description"})
            else:
                return None

        if "amount" not in df.columns:
            num_cols = [
                c for c in df.columns
                if pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.6
            ]
            if num_cols:
                df = df.rename(columns={num_cols[0]: "amount"})
            else:
                return None

        # Type coercions.
        df["amount"]           = pd.to_numeric(df["amount"], errors="coerce").abs().fillna(0)
        df["transaction_type"] = df.get(
            "transaction_type", pd.Series(["Debit"] * len(df))
        ).fillna("Debit")
        df["balance"]          = pd.to_numeric(
            df.get("balance", pd.Series([0.0] * len(df))), errors="coerce"
        ).fillna(0)
        df["date"]             = df.get(
            "date", pd.Series(["01-01-2024"] * len(df))
        ).astype(str).fillna("01-01-2024")
        df["transaction_id"]   = [f"{id(df)}_{i}" for i in range(len(df))]

        df = df[df["amount"] > 0].reset_index(drop=True)
        return df

    # ── Daily spend builder ────────────────────────────────────────────

    def _build_daily_spend(self, txn_list: list) -> list[dict]:
        daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for t in txn_list:
            if _is_debit(t.get("transaction_type", "Debit")):
                daily[str(t.get("date", ""))][t.get("category", "Other")] \
                    += float(t.get("amount", 0))
        return [
            {"date": d, "category_amounts": dict(cats)}
            for d, cats in sorted(daily.items())
        ]

    # ── Health ─────────────────────────────────────────────────────────

    def get_model_health(self) -> dict:
        cat_ok = self.categorizer.is_loaded()
        ano_ok = self.anomaly_detector.is_loaded()
        for_ok = self.forecaster.is_loaded()
        pol_ok = self.policy_learner.is_loaded()
        return {
            "categorizer_loaded":      cat_ok,
            "anomaly_detector_loaded": ano_ok,
            "forecaster_loaded":       for_ok,
            "policy_learner_loaded":   pol_ok,
            "all_healthy":             all([cat_ok, ano_ok, for_ok, pol_ok]),
            "models_active":           self._active_models(),
        }

    def _active_models(self) -> list[str]:
        active = []
        if self.categorizer.is_loaded():      active.append("categorizer_ml")
        else:                                  active.append("categorizer_rules")
        if self.anomaly_detector.is_loaded(): active.append("anomaly_isolation_forest")
        else:                                  active.append("anomaly_zscore")
        if self.forecaster.is_loaded():       active.append("forecaster_bilstm")
        else:                                  active.append("forecaster_moving_avg")
        if self.policy_learner.is_loaded():   active.append("budget_qlearning")
        else:                                  active.append("budget_rules")
        return active