"""
intelligence/anomaly_detector.py
─────────────────────────────────────────────────────────────────────────────
Detects spending anomalies using IsolationForest + rule-based checks.

Anomaly types:
    SPIKE        — amount >> user category average (DEBIT only)
    DUPLICATE    — same merchant, same amount ±5 %, within 24 h,
                   excluding known recurring merchants
    OFF_HOURS    — transaction between 01:00–05:00
    NEW_MERCHANT — unseen merchant + amount > ₹2 000
    VELOCITY     — >5 transactions in the same 60-min window
                   (disabled automatically when CSV has no HH:MM:SS)

Falls back to z-score rules when IsolationForest model files are absent.

Example
-------
    detector = AnomalyDetector()
    result   = detector.detect(txn, history)
    # AnomalyResult(is_anomaly=True, anomaly_type='SPIKE', severity='HIGH')
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import joblib
import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

MODEL_DIR = "models/isolation_forest"

# Merchants that repeat daily/weekly by design — never flag as duplicate.
RECURRING_MERCHANTS: frozenset[str] = frozenset({
    "zomato", "swiggy", "blinkit", "zepto", "dunzo",
    "ola", "uber", "rapido", "namma yatri",
    "delhi metro", "dmrc", "mumbai metro", "bmtc",
    "chai point", "starbucks", "cafe coffee day",
    "mcdonald", "domino", "kfc", "subway",
    "netflix", "spotify", "hotstar", "prime video",
    "electricity", "water bill", "gas bill",
})

# Transaction types that represent inflows — never score these for SPIKE.
CREDIT_TYPES: frozenset[str] = frozenset({
    "credit", "cr", "received", "inward", "refund",
    "cashback", "reversal", "salary", "interest",
})

# Duplicate detection window.
DUPLICATE_WINDOW_HOURS: int = 24


# ── Value object ──────────────────────────────────────────────────────────────

class AnomalyResult:
    """Immutable result returned by AnomalyDetector.detect()."""

    __slots__ = (
        "transaction_id", "is_anomaly", "anomaly_score",
        "anomaly_type", "severity", "reason", "model_source",
    )

    def __init__(
        self,
        transaction_id: str,
        is_anomaly: bool,
        anomaly_score: float,
        anomaly_type: str | None,
        severity: str,
        reason: str,
        model_source: str,
    ) -> None:
        self.transaction_id = transaction_id
        self.is_anomaly     = is_anomaly
        self.anomaly_score  = round(anomaly_score, 4)
        self.anomaly_type   = anomaly_type   # SPIKE|DUPLICATE|OFF_HOURS|NEW_MERCHANT|VELOCITY
        self.severity       = severity       # LOW|MEDIUM|HIGH
        self.reason         = reason
        self.model_source   = model_source

    def dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    def __repr__(self) -> str:
        return (
            f"AnomalyResult(id={self.transaction_id!r}, "
            f"anomaly={self.is_anomaly}, type={self.anomaly_type!r}, "
            f"severity={self.severity!r})"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(obj, key: str, default=None):
    """Attribute or dict access — works with both transaction formats."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_dt(txn, fmt: str = "%d-%m-%Y") -> datetime | None:
    """Parse transaction date; return None on failure."""
    raw = str(_get(txn, "date", "")).strip()
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        return None


def _is_credit(txn) -> bool:
    """Return True if the transaction represents an inflow."""
    txn_type = str(_get(txn, "transaction_type", "Debit")).strip().lower()
    return txn_type in CREDIT_TYPES


def _has_time_column(history: list) -> bool:
    """
    Return True only if at least one historical record has a non-trivial
    time field (i.e. something beyond midnight / blank).

    Used to gate the VELOCITY rule — CSV exports often have no HH:MM:SS,
    making every same-day transaction appear within the same 60-min window.
    """
    for h in history[:50]:
        t = str(_get(h, "time", "")).strip()
        if t and t not in {"00:00:00", "00:00", ""}:
            return True
    return False


# ── Main class ────────────────────────────────────────────────────────────────

class AnomalyDetector:
    """Detects spending anomalies using IsolationForest + rule-based checks."""

    # Class-level merchant memory (shared across calls in the same process).
    KNOWN_MERCHANTS: set[str] = set()

    def __init__(self, model_dir: str = MODEL_DIR) -> None:
        self._model_dir = model_dir
        self._model     = None
        self._scaler    = None
        self._cat_stats: dict = {}
        self._loaded    = False
        self._load()

    # ── Initialisation ─────────────────────────────────────────────────

    def _load(self) -> None:
        m_path  = os.path.join(self._model_dir, "model.joblib")
        s_path  = os.path.join(self._model_dir, "scaler.joblib")
        cs_path = os.path.join(self._model_dir, "category_stats.json")

        if not (os.path.exists(m_path) and os.path.exists(s_path)):
            print("[AnomalyDetector] ⚠  Model not found — using z-score fallback.")
            return
        try:
            self._model  = joblib.load(m_path)
            self._scaler = joblib.load(s_path)
            if os.path.exists(cs_path):
                with open(cs_path) as f:
                    self._cat_stats = json.load(f)
            self._loaded = True
            print("[AnomalyDetector] ✅ IsolationForest loaded.")
        except Exception as exc:
            print(f"[AnomalyDetector] ⚠  Load error: {exc}")

    def is_loaded(self) -> bool:
        return self._loaded

    # ── Public API ─────────────────────────────────────────────────────

    def detect(self, transaction, history: list) -> AnomalyResult:
        """
        Detect anomaly for a single transaction given user history.

        Fix #1 — Credits are never scored for SPIKE/anomalies.
        They pass through as LOW / normal immediately.

        Args:
            transaction : Transaction dict or object.
            history     : List of past Transaction dicts/objects.

        Returns:
            AnomalyResult
        """
        txn_id   = _get(transaction, "transaction_id", "unknown")
        amount   = float(_get(transaction, "amount", 0.0))
        category = _get(transaction, "category", "Other") or "Other"
        merchant = str(_get(transaction, "description", "")).strip()

        # ── FIX #1 ── Credit transactions are income/refunds, never anomalies.
        if _is_credit(transaction):
            return AnomalyResult(
                txn_id, False, 0.50, None, "LOW",
                "Credit transaction — inflow, not scored.",
                "rule_check",
            )

        dt = _parse_dt(transaction)
        hour = dt.hour if dt else 12

        # ── Rule checks (always run first — fast) ──────────────────────

        # 1. DUPLICATE — same merchant, same amount ±5 %, within 24 h
        dup = self._check_duplicate(transaction, history)
        if dup:
            return dup

        # 2. OFF_HOURS — 01:00–05:00
        if 1 <= hour <= 5 and amount > 500:
            severity = "HIGH" if amount > 3_000 else "MEDIUM"
            return AnomalyResult(
                txn_id, True, -0.80, "OFF_HOURS", severity,
                f"₹{amount:,.0f} transaction at {hour:02d}:00 — unusual hour.",
                "rule_check",
            )

        # 3. NEW_MERCHANT — first time + high value
        if (
            merchant not in self.KNOWN_MERCHANTS
            and amount > 2_000
            and len(self.KNOWN_MERCHANTS) > 10
        ):
            self.KNOWN_MERCHANTS.add(merchant)
            return AnomalyResult(
                txn_id, True, -0.65, "NEW_MERCHANT", "MEDIUM",
                f"First-time transaction of ₹{amount:,.0f} at new merchant.",
                "rule_check",
            )
        self.KNOWN_MERCHANTS.add(merchant)

        # 4. VELOCITY — >5 debits in last 60 min
        #    FIX #3: skip entirely when the data has no time column.
        if _has_time_column(history) and self._check_velocity(transaction, history) >= 5:
            return AnomalyResult(
                txn_id, True, -0.70, "VELOCITY", "HIGH",
                "More than 5 transactions in the last hour — possible fraud.",
                "rule_check",
            )

        # ── ML / z-score ────────────────────────────────────────────────
        if len(history) < 10:
            return self._zscore_check(txn_id, amount, category, history)

        if self._loaded:
            return self._ml_detect(transaction, history)
        return self._zscore_check(txn_id, amount, category, history)

    def detect_batch(self, transactions: list, history: list) -> list[AnomalyResult]:
        """Detect anomalies for a list of transactions."""
        return [self.detect(t, history) for t in transactions]

    def retrain_for_user(self, user_id: str, transactions: list) -> bool:
        """
        Retrain IsolationForest on a specific user's transaction history.
        Called after a user accumulates >50 new transactions.
        """
        if len(transactions) < 30:
            return False
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            X      = self._featurize_batch(transactions)
            scaler = StandardScaler()
            Xs     = scaler.fit_transform(X)
            model  = IsolationForest(
                n_estimators=150, contamination=0.06, random_state=42
            )
            model.fit(Xs)

            user_dir = os.path.join(self._model_dir, "user_models", user_id)
            os.makedirs(user_dir, exist_ok=True)
            joblib.dump(model,  os.path.join(user_dir, "model.joblib"))
            joblib.dump(scaler, os.path.join(user_dir, "scaler.joblib"))
            return True
        except Exception as exc:
            print(f"[AnomalyDetector] retrain error for {user_id}: {exc}")
            return False

    # ── Feature engineering ────────────────────────────────────────────

    def _cat_stat(self, category: str, history: list, stat: str) -> float:
        # Only use debit history for baseline stats.
        amounts = [
            float(_get(t, "amount", 0))
            for t in history
            if _get(t, "category", "") == category and not _is_credit(t)
        ]
        if len(amounts) < 3:
            defaults = {"mean": 500, "std": 150, "median": 450}
            return defaults.get(stat, 500)
        arr = np.array(amounts)
        if stat == "mean":   return float(arr.mean())
        if stat == "std":    return float(max(arr.std(), 1.0))
        if stat == "median": return float(np.median(arr))
        return float(arr.mean())

    def _featurize_one(self, txn, history: list) -> np.ndarray:
        amount   = float(_get(txn, "amount", 0))
        category = _get(txn, "category", "Other") or "Other"
        desc     = str(_get(txn, "description", ""))

        dt  = _parse_dt(txn)
        hour = dt.hour      if dt else 12
        dow  = dt.weekday() if dt else 0

        mean   = self._cat_stat(category, history, "mean")
        std    = self._cat_stat(category, history, "std")
        median = self._cat_stat(category, history, "median")

        amt_norm   = amount / (mean   + 1e-9)
        zscore     = (amount - mean) / (std + 1e-9)
        amt_median = amount / (median + 1e-9)

        # Days since same merchant (capped at 30)
        days_since = 30.0
        for h in reversed(history[-60:]):
            if str(_get(h, "description", "")) == desc:
                h_dt = _parse_dt(h)
                if h_dt and dt:
                    days_since = min(30.0, abs((dt - h_dt).days))
                break

        return np.array(
            [[amt_norm, hour, dow, zscore, days_since, amt_median]],
            dtype=np.float32,
        )

    def _featurize_batch(self, transactions: list) -> np.ndarray:
        return np.vstack([self._featurize_one(t, transactions) for t in transactions])

    # ── ML detection ──────────────────────────────────────────────────

    def _ml_detect(self, txn, history: list) -> AnomalyResult:
        txn_id   = _get(txn, "transaction_id", "unknown")
        amount   = float(_get(txn, "amount", 0))
        category = _get(txn, "category", "Other") or "Other"

        try:
            X    = self._featurize_one(txn, history)
            Xs   = self._scaler.transform(X)
            pred = int(self._model.predict(Xs)[0])
            score = float(self._model.score_samples(Xs)[0])

            if pred == -1:
                mean  = self._cat_stat(category, history, "mean")
                ratio = amount / (mean + 1e-9)

                # ✓ SPIKE severity: ratio-based thresholds (not score-based).
                if ratio >= 3.0 or ratio <= 0.1:
                    severity = "HIGH"
                elif ratio >= 2.0 or ratio <= 0.15:
                    severity = "MEDIUM"
                else:
                    return AnomalyResult(txn_id, False, score, None,
                                         "LOW", "Transaction within normal range.",
                                         "isolation_forest")

                reason = (
                    f"₹{amount:,.0f} on {category} is {ratio:.1f}× your average "
                    f"of ₹{mean:,.0f}."
                )
                return AnomalyResult(
                    txn_id, True, score, "SPIKE", severity, reason,
                    "isolation_forest",
                )

            return AnomalyResult(
                txn_id, False, score, None, "LOW",
                "Transaction within normal range.",
                "isolation_forest",
            )

        except Exception as exc:
            print(f"[AnomalyDetector] ML error: {exc}")
            return self._zscore_check(
                txn_id, float(_get(txn, "amount", 0)), category, history
            )

    # ── Z-score fallback ──────────────────────────────────────────────

    def _zscore_check(
        self, txn_id: str, amount: float, category: str, history: list
    ) -> AnomalyResult:
        mean = self._cat_stat(category, history, "mean")
        std  = self._cat_stat(category, history, "std")
        z    = abs((amount - mean) / (std + 1e-9))

        if z > 3.5:
            return AnomalyResult(
                txn_id, True, -0.90, "SPIKE", "HIGH",
                f"₹{amount:,.0f} is {z:.1f}σ above your {category} average "
                f"of ₹{mean:,.0f}.",
                "zscore_fallback",
            )
        if z > 2.0:
            return AnomalyResult(
                txn_id, True, -0.55, "SPIKE", "MEDIUM",
                f"₹{amount:,.0f} is {z:.1f}σ above your {category} average.",
                "zscore_fallback",
            )
        return AnomalyResult(
            txn_id, False, 0.50, None, "LOW",
            "Transaction within normal range.",
            "zscore_fallback",
        )

    # ── Rule helpers ──────────────────────────────────────────────────

    def _check_duplicate(self, txn, history: list) -> AnomalyResult | None:
        """
        FIX #1 — Duplicate detection with:
          • 24-hour time window  (was: unlimited lookback)
          • Recurring merchant whitelist  (was: none)
        """
        txn_id = _get(txn, "transaction_id", "unknown")
        amount = float(_get(txn, "amount", 0))
        desc   = str(_get(txn, "description", "")).strip()

        # Skip known recurring merchants — they legitimately repeat.
        desc_lower = desc.lower()
        if any(r in desc_lower for r in RECURRING_MERCHANTS):
            return None

        txn_dt = _parse_dt(txn)
        if txn_dt is None:
            return None  # can't compute window without a valid date

        for h in history[-100:]:
            h_id = _get(h, "transaction_id", "")
            if h_id == txn_id:
                continue
            h_desc = str(_get(h, "description", "")).strip()
            if h_desc != desc:
                continue

            # ── KEY FIX: only flag within DUPLICATE_WINDOW_HOURS ────────
            h_dt = _parse_dt(h)
            if h_dt is None:
                continue
            if abs((txn_dt - h_dt).days) > (DUPLICATE_WINDOW_HOURS // 24):
                continue  # outside window — not a duplicate

            h_amount = float(_get(h, "amount", 0))
            if abs(h_amount - amount) / (amount + 1e-9) < 0.05:
                return AnomalyResult(
                    txn_id, True, -0.95, "DUPLICATE", "HIGH",
                    f"Possible duplicate charge of ₹{amount:,.0f} at {desc}.",
                    "rule_check",
                )
        return None

    def _check_velocity(self, txn, history: list) -> int:
        """
        Count debit transactions in the same 60-minute window.

        FIX #3 — This method is only called when _has_time_column() is True,
        so the guard below is a defensive fallback only.
        """
        txn_dt = _parse_dt(txn)
        if txn_dt is None:
            return 0

        # If all timestamps look like midnight, data has no real time info.
        txn_time = str(_get(txn, "time", "")).strip()
        if not txn_time or txn_time in {"00:00:00", "00:00"}:
            return 0

        count = 0
        for h in history[-50:]:
            if _is_credit(h):
                continue  # only count debits toward velocity
            h_dt = _parse_dt(h)
            if h_dt and abs((txn_dt - h_dt).total_seconds()) <= 3_600:
                count += 1
        return count