"""
memory/trajectory_memory.py — Tier 5: Behavioral trajectory on Atlas Time Series.

Stores weekly behavioral snapshots in a MongoDB Time Series collection.
Each snapshot captures spending velocity, savings rate, archetype, and goal adherence.

Archetype classification rules (exact deterministic logic):
  impulse_spender_reward_driven — weekend/weekday ratio > 1.5 AND gain framing preferred
  disciplined_saver             — savings_rate > 0.20 AND goal_adherence > 0.75
  volatile_spender              — anomaly_frequency_30d > 5
  income_anxious                — income_stability_score < 0.55
  goal_oriented_planner         — goal_adherence > 0.60 AND savings_rate > 0.10
  balanced_optimizer            — everything else

Collection: trajectory_snapshots (Time Series)
  timeField : "timestamp"
  metaField : "metadata"  ← contains user_id

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import BehavioralArchetype, SavingsTrend, TrajectoryMemory

logger = logging.getLogger(__name__)

_COLLECTION = "trajectory_snapshots"


class TrajectoryMemoryStore:
    """
    Atlas Time Series-backed Tier 5 behavioral trajectory.

    Usage:
        store = TrajectoryMemoryStore(db)
        snapshot = await store.recompute_snapshot("user-1", transactions)
        await store.insert_snapshot("user-1", snapshot)
        latest = await store.get_latest_snapshot("user-1")
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[_COLLECTION]

    # ──────────────────────────────────────────────────────────────────────────
    # READS
    # ──────────────────────────────────────────────────────────────────────────

    async def get_latest_snapshot(self, user_id: str) -> Optional[TrajectoryMemory]:
        """
        Retrieve the most recent trajectory snapshot for a user.

        Args:
            user_id: User identifier.

        Returns:
            Most recent TrajectoryMemory, or None if no snapshots exist.

        Example:
            >>> traj = await store.get_latest_snapshot("user-1")
            >>> traj.behavioral_archetype
            <BehavioralArchetype.DISCIPLINED_SAVER: 'disciplined_saver'>
        """
        try:
            cursor = (
                self._col.find({"metadata.user_id": user_id})
                .sort("timestamp", -1)
                .limit(1)
            )
            docs = await cursor.to_list(length=1)
            return _doc_to_trajectory(docs[0]) if docs else None
        except Exception as exc:
            logger.warning(f"[TRAJECTORY] Latest snapshot failed: {exc}")
            return None

    async def get_snapshots(
        self, user_id: str, days_back: int = 90, limit: int = 12
    ) -> List[TrajectoryMemory]:
        """
        Retrieve recent trajectory snapshots for trend analysis.

        Args:
            user_id: User identifier.
            days_back: Lookback window in days.
            limit: Maximum snapshots to return.

        Returns:
            List of TrajectoryMemory sorted by timestamp DESC.

        Example:
            >>> snapshots = await store.get_snapshots("user-1", days_back=30)
        """
        since = datetime.utcnow() - timedelta(days=days_back)
        try:
            cursor = (
                self._col.find({
                    "metadata.user_id": user_id,
                    "timestamp"       : {"$gte": since},
                })
                .sort("timestamp", -1)
                .limit(limit)
            )
            docs = await cursor.to_list(length=limit)
            return [_doc_to_trajectory(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[TRAJECTORY] Snapshot history failed: {exc}")
            return []

    async def retrieve(
        self,
        user_id: str,
        limit: int = 1,
        query_embedding: Optional[object] = None,
    ) -> Optional[TrajectoryMemory]:
        """Backward-compatible interface — returns latest snapshot."""
        return await self.get_latest_snapshot(user_id)

    # ──────────────────────────────────────────────────────────────────────────
    # WRITES
    # ──────────────────────────────────────────────────────────────────────────

    async def insert_snapshot(
        self, user_id: str, snapshot: TrajectoryMemory
    ) -> None:
        """
        Insert a trajectory snapshot into the Time Series collection.

        Uses Atlas Time Series format:
          timestamp: datetime  ← timeField
          metadata : {user_id} ← metaField
          + all snapshot fields

        Args:
            user_id: User identifier.
            snapshot: Computed TrajectoryMemory to persist.

        Example:
            >>> await store.insert_snapshot("user-1", computed_snapshot)
        """
        doc = {
            "timestamp": datetime.utcnow(),
            "metadata" : {"user_id": user_id},
            # Scalar trajectory fields
            "snapshot_date"             : snapshot.snapshot_date.isoformat(),
            "spending_velocity_7d"      : snapshot.spending_velocity_7d,
            "spending_velocity_30d"     : snapshot.spending_velocity_30d,
            "savings_rate_current"      : snapshot.savings_rate_current,
            "savings_rate_trend"        : snapshot.savings_rate_trend.value if snapshot.savings_rate_trend else None,
            "income_stability_score"    : snapshot.income_stability_score,
            "goal_adherence_score"      : snapshot.goal_adherence_score,
            "behavioral_archetype"      : snapshot.behavioral_archetype.value,
            "weekday_weekend_ratio"     : snapshot.weekday_weekend_ratio,
            "top_3_categories"          : snapshot.top_3_categories,
            "anomaly_frequency_30d"     : snapshot.anomaly_frequency_30d,
            "response_pattern"          : snapshot.response_pattern,
        }
        try:
            await self._col.insert_one(doc)
        except Exception as exc:
            logger.warning(f"[TRAJECTORY] Insert snapshot failed: {exc}")

    # ──────────────────────────────────────────────────────────────────────────
    # COMPUTATION
    # ──────────────────────────────────────────────────────────────────────────

    async def recompute_snapshot(
        self,
        user_id: str,
        transactions: List[Dict],
        income: float = 0.0,
        active_goals: Optional[List[Dict]] = None,
        prev_snapshots: Optional[List[TrajectoryMemory]] = None,
    ) -> TrajectoryMemory:
        """
        Recompute a full trajectory snapshot from raw transaction data.

        All computation is deterministic — no LLM calls.

        Metrics computed:
          spending_velocity_7d  = (sum_last7 - sum_prev7) / max(sum_prev7, 1) * 100
          spending_velocity_30d = same for 30d
          savings_rate_current  = (income - total_spend_30d) / income
          savings_rate_trend    = compare to last 2 snapshots
          income_stability_score = 1 - (income_std / income_mean)
          goal_adherence_score   = goals_on_track / total_goals
          weekday_weekend_ratio  = weekend_spend / max(weekday_spend, 1)
          anomaly_frequency_30d  = count anomalies in past 30d

        Args:
            user_id: User identifier.
            transactions: List of dicts with keys: amount, date, is_credit, is_anomaly,
                          day_of_week (0=Mon, 6=Sun).
            income: Known monthly income (0 = estimate from credits).
            active_goals: List of goal dicts with target_amount, current_amount.
            prev_snapshots: Previous trajectory snapshots for trend comparison.

        Returns:
            Fully populated TrajectoryMemory (not yet persisted).

        Example:
            >>> snap = await store.recompute_snapshot("user-1", txns, income=50000)
            >>> snap.behavioral_archetype
            <BehavioralArchetype.IMPULSE_SPENDER: 'impulse_spender_reward_driven'>
        """
        import math
        from datetime import date

        now         = datetime.utcnow()
        today       = now.date()

        expenses = [
            t for t in transactions
            if not t.get("is_credit", False)
        ]

        def _txn_date(t) -> date:
            d = t.get("date") or t.get("transaction_date") or now
            if isinstance(d, datetime):
                return d.date()
            if isinstance(d, date):
                return d
            try:
                return datetime.fromisoformat(str(d)).date()
            except Exception:
                return today

        def _days_ago(d: date) -> int:
            return (today - d).days

        # ── Spending velocity ─────────────────────────────────────────────────
        sum_last7  = sum(t["amount"] for t in expenses if _days_ago(_txn_date(t)) <= 7)
        sum_prev7  = sum(t["amount"] for t in expenses if 7 < _days_ago(_txn_date(t)) <= 14)
        sum_last30 = sum(t["amount"] for t in expenses if _days_ago(_txn_date(t)) <= 30)
        sum_prev30 = sum(t["amount"] for t in expenses if 30 < _days_ago(_txn_date(t)) <= 60)

        velocity_7d  = ((sum_last7 - sum_prev7)  / max(sum_prev7, 1)) * 100
        velocity_30d = ((sum_last30 - sum_prev30) / max(sum_prev30, 1)) * 100

        # ── Savings rate ──────────────────────────────────────────────────────
        if income <= 0:
            # Estimate from credits
            income = sum(
                t["amount"] for t in transactions
                if t.get("is_credit") and _days_ago(_txn_date(t)) <= 30
            )
        savings_rate = max(0.0, (income - sum_last30) / max(income, 1))

        # ── Savings rate trend ────────────────────────────────────────────────
        if prev_snapshots and len(prev_snapshots) >= 2:
            prev_rates = [s.savings_rate_current or 0 for s in prev_snapshots[:2]]
            avg_prev   = sum(prev_rates) / len(prev_rates)
            if savings_rate > avg_prev + 0.02:
                savings_trend = SavingsTrend.IMPROVING
            elif savings_rate < avg_prev - 0.02:
                savings_trend = SavingsTrend.DECLINING
            else:
                savings_trend = SavingsTrend.STABLE
        else:
            savings_trend = SavingsTrend.STABLE

        # ── Income stability ──────────────────────────────────────────────────
        monthly_credits: List[float] = []
        for t in transactions:
            if t.get("is_credit"):
                monthly_credits.append(float(t.get("amount", 0)))

        if len(monthly_credits) >= 2:
            mean_inc = sum(monthly_credits) / len(monthly_credits)
            std_inc  = math.sqrt(
                sum((x - mean_inc) ** 2 for x in monthly_credits) / len(monthly_credits)
            )
            income_stability = max(0.0, 1.0 - std_inc / max(mean_inc, 1))
        else:
            income_stability = 0.7  # neutral for new users

        # ── Goal adherence ────────────────────────────────────────────────────
        if active_goals:
            on_track = sum(
                1 for g in active_goals
                if g.get("current_amount", 0) / max(g.get("target_amount", 1), 1) >= 0.10
            )
            goal_adherence = on_track / max(len(active_goals), 1)
        else:
            goal_adherence = 0.5

        # ── Weekday/weekend ratio ─────────────────────────────────────────────
        weekend_spend = sum(
            t["amount"] for t in expenses
            if _txn_date(t).weekday() >= 5   # 5=Sat, 6=Sun
        )
        weekday_spend = sum(
            t["amount"] for t in expenses
            if _txn_date(t).weekday() < 5
        )
        ww_ratio = weekend_spend / max(weekday_spend, 1)

        # ── Anomaly frequency ─────────────────────────────────────────────────
        anomaly_count = sum(
            1 for t in expenses
            if t.get("is_anomaly") and _days_ago(_txn_date(t)) <= 30
        )

        # ── Top categories ────────────────────────────────────────────────────
        from collections import Counter
        cat_spend: Counter = Counter()
        for t in expenses:
            if _days_ago(_txn_date(t)) <= 30:
                cat_spend[t.get("category", "unknown")] += t.get("amount", 0)
        top_3 = [cat for cat, _ in cat_spend.most_common(3)]

        # ── Archetype classification ──────────────────────────────────────────
        archetype = classify_archetype(
            weekday_weekend_ratio = ww_ratio,
            savings_rate          = savings_rate,
            goal_adherence        = goal_adherence,
            anomaly_frequency     = anomaly_count,
            income_stability      = income_stability,
        )

        return TrajectoryMemory(
            id                       = "",    # not persisted yet
            user_id                  = user_id,
            snapshot_date            = today,
            spending_velocity_7d     = round(velocity_7d, 2),
            spending_velocity_30d    = round(velocity_30d, 2),
            savings_rate_current     = round(savings_rate, 4),
            savings_rate_trend       = savings_trend,
            income_stability_score   = round(income_stability, 4),
            goal_adherence_score     = round(goal_adherence, 4),
            behavioral_archetype     = archetype,
            weekday_weekend_ratio    = round(ww_ratio, 3),
            top_3_categories         = top_3,
            anomaly_frequency_30d    = anomaly_count,
            response_pattern         = {},
        )


# ─────────────────────────────────────────────────────────────────────────────
# ARCHETYPE CLASSIFICATION (deterministic rule set)
# ─────────────────────────────────────────────────────────────────────────────

def classify_archetype(
    weekday_weekend_ratio: float,
    savings_rate: float,
    goal_adherence: float,
    anomaly_frequency: int,
    income_stability: float,
) -> BehavioralArchetype:
    """
    Deterministic 6-class archetype classification.

    Rule priority order (first match wins):
      1. impulse_spender_reward_driven — weekend/weekday > 1.5
      2. disciplined_saver             — savings_rate > 0.20 AND goal_adherence > 0.75
      3. volatile_spender              — anomaly_frequency > 5
      4. income_anxious                — income_stability < 0.55
      5. goal_oriented_planner         — goal_adherence > 0.60 AND savings_rate > 0.10
      6. balanced_optimizer            — fallback

    Args:
        weekday_weekend_ratio: weekend_spend / weekday_spend.
        savings_rate: (income - expenses) / income, 0–1.
        goal_adherence: goals_on_track / total_goals, 0–1.
        anomaly_frequency: Count of anomalies in past 30 days.
        income_stability: 1 - (income_std / income_mean), 0–1.

    Returns:
        BehavioralArchetype enum value.

    Example:
        >>> classify_archetype(2.0, 0.05, 0.3, 2, 0.8)
        <BehavioralArchetype.IMPULSE_SPENDER: 'impulse_spender_reward_driven'>
        >>> classify_archetype(0.8, 0.25, 0.80, 1, 0.9)
        <BehavioralArchetype.DISCIPLINED_SAVER: 'disciplined_saver'>
    """
    if weekday_weekend_ratio > 1.5:
        return BehavioralArchetype.IMPULSE_SPENDER

    if savings_rate > 0.20 and goal_adherence > 0.75:
        return BehavioralArchetype.DISCIPLINED_SAVER

    if anomaly_frequency > 5:
        return BehavioralArchetype.VOLATILE_SPENDER

    if income_stability < 0.55:
        return BehavioralArchetype.INCOME_ANXIOUS

    if goal_adherence > 0.60 and savings_rate > 0.10:
        return BehavioralArchetype.GOAL_ORIENTED

    return BehavioralArchetype.UNKNOWN   # "balanced_optimizer" in display


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_trajectory(doc: dict) -> TrajectoryMemory:
    """Convert Time Series document to TrajectoryMemory Pydantic model."""
    from datetime import date
    meta    = doc.get("metadata", {})
    user_id = meta.get("user_id", "")

    snap_date_raw = doc.get("snapshot_date", "")
    try:
        snap_date = date.fromisoformat(snap_date_raw) if snap_date_raw else date.today()
    except Exception:
        snap_date = date.today()

    try:
        arch = BehavioralArchetype(doc.get("behavioral_archetype", "unknown"))
    except ValueError:
        arch = BehavioralArchetype.UNKNOWN

    trend_val = doc.get("savings_rate_trend")
    try:
        trend = SavingsTrend(trend_val) if trend_val else SavingsTrend.STABLE
    except ValueError:
        trend = SavingsTrend.STABLE

    return TrajectoryMemory(
        id                       = str(doc.get("_id", "")),
        user_id                  = user_id,
        snapshot_date            = snap_date,
        spending_velocity_7d     = doc.get("spending_velocity_7d"),
        spending_velocity_30d    = doc.get("spending_velocity_30d"),
        savings_rate_current     = doc.get("savings_rate_current"),
        savings_rate_trend       = trend,
        income_stability_score   = doc.get("income_stability_score"),
        goal_adherence_score     = doc.get("goal_adherence_score"),
        behavioral_archetype     = arch,
        weekday_weekend_ratio    = doc.get("weekday_weekend_ratio"),
        top_3_categories         = doc.get("top_3_categories", []),
        anomaly_frequency_30d    = int(doc.get("anomaly_frequency_30d", 0)),
        response_pattern         = doc.get("response_pattern", {}),
        created_at               = doc.get("timestamp", datetime.utcnow()),
    )
