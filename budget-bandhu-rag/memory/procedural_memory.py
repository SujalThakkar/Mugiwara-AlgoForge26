"""
memory/procedural_memory.py — Tier 4: Strategy library on Atlas.

Stores reusable advice strategies with EMA-based success rate learning.
Strategies are matched by event_type + behavioral archetype and updated
based on user responses.

Collection: procedural_memory
Default strategies (seeded for new users):
  1. soft_nudge_positive_frame   — gentle + gain framing
  2. strict_alert_loss_frame     — strict + loss framing
  3. goal_progress_anchor        — motivational + neutral
  4. category_deep_dive          — analytical + neutral
  5. weekend_pattern_nudge       — gentle + loss framing
  6. subscription_surface        — analytical + gain framing

Author: Aryan Lomte
Version: 3.0.0
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from models.schemas import ProceduralMemory

logger = logging.getLogger(__name__)

_COLLECTION  = "procedural_memory"
_EMA_ALPHA   = 0.3   # EMA smoothing factor for success rate

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT STRATEGY DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_STRATEGIES = [
    {
        "strategy_id"      : "soft_nudge_positive_frame",
        "trigger_condition": {"event_type": "OVERSPEND"},
        "user_condition"   : {"archetype": "impulse_spender_reward_driven"},
        "action_template"  : (
            "Acknowledge the overspend without judgement. "
            "Frame the alternative as a GAIN: 'Saving Rs.{amount} this week brings you "
            "{pct}% closer to {goal}.' Use warm, encouraging tone."
        ),
        "tone_override": "gentle",
    },
    {
        "strategy_id"      : "strict_alert_loss_frame",
        "trigger_condition": {"event_type": "OVERSPEND"},
        "user_condition"   : {"archetype": "disciplined_saver"},
        "action_template"  : (
            "State the shortfall directly. "
            "Frame as a LOSS: 'This Rs.{amount} overspend delays {goal} by {days} days.' "
            "Provide a concrete corrective action with a deadline. Use analytical tone."
        ),
        "tone_override": "strict",
    },
    {
        "strategy_id"      : "goal_progress_anchor",
        "trigger_condition": {"event_type": "SAVINGS_MILESTONE"},
        "user_condition"   : None,
        "action_template"  : (
            "Celebrate the milestone. Show progress: 'You are {pct}% of the way to {goal}.' "
            "Suggest the next micro-milestone. Use motivational tone."
        ),
        "tone_override": "motivational",
    },
    {
        "strategy_id"      : "category_deep_dive",
        "trigger_condition": {"event_type": "TREND_QUERY"},
        "user_condition"   : None,
        "action_template"  : (
            "Present a 30-day breakdown of {category} spending with week-over-week delta. "
            "Identify top 3 merchants. Suggest one specific reduction. Use analytical tone."
        ),
        "tone_override": "analytical",
    },
    {
        "strategy_id"      : "weekend_pattern_nudge",
        "trigger_condition": {"event_type": "ANOMALY"},
        "user_condition"   : {"archetype": "impulse_spender_reward_driven"},
        "action_template"  : (
            "Note the weekend spike gently. "
            "Suggest a pre-approved 'fun budget': 'Setting aside Rs.{budget} for weekends "
            "gives you freedom without guilt.' Avoid lecture tone."
        ),
        "tone_override": "gentle",
    },
    {
        "strategy_id"      : "subscription_surface",
        "trigger_condition": {"event_type": "SUBSCRIPTION_AUDIT"},
        "user_condition"   : None,
        "action_template"  : (
            "List all detected subscriptions with monthly + annual cost. "
            "Flag ones unused in past 30 days. "
            "Calculate total annual savings from cancellation. Use analytical tone."
        ),
        "tone_override": "analytical",
    },
]


class ProceduralMemoryStore:
    """
    Atlas-backed Tier 4 strategy library.

    Usage:
        store = ProceduralMemoryStore(db)
        await store.seed_default_strategies("user-1")
        strategy = await store.get_best_strategy("user-1", "OVERSPEND", "impulse_spender")
        await store.update_outcome(strategy.strategy_id, "user-1", success=True)
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[_COLLECTION]

    # ──────────────────────────────────────────────────────────────────────────
    # SETUP
    # ──────────────────────────────────────────────────────────────────────────

    async def seed_default_strategies(self, user_id: str) -> int:
        """
        Seed 6 default strategies for a new user if not already present.

        Idempotent — uses upsert so re-runs are safe.

        Args:
            user_id: New user to seed strategies for.

        Returns:
            Count of strategies inserted (0 if already seeded).

        Example:
            >>> n = await store.seed_default_strategies("user-123")
            >>> n
            6
        """
        now = datetime.utcnow()
        count = 0
        for tpl in _DEFAULT_STRATEGIES:
            doc = {
                **tpl,
                "user_id"      : user_id,
                "success_count": 0,
                "failure_count": 0,
                "success_rate" : 0.5,
                "last_applied" : None,
                "last_outcome" : None,
                "created_at"   : now,
                "updated_at"   : now,
            }
            try:
                result = await self._col.update_one(
                    {"user_id": user_id, "strategy_id": tpl["strategy_id"]},
                    {"$setOnInsert": {**doc, "id": str(uuid.uuid4())}},
                    upsert=True,
                )
                if result.upserted_id:
                    count += 1
            except Exception as exc:
                logger.warning(f"[PROCEDURAL] Seed error for {tpl['strategy_id']}: {exc}")

        logger.info(f"[PROCEDURAL] Seeded {count} strategies for user {user_id}")
        return count

    # ──────────────────────────────────────────────────────────────────────────
    # READS
    # ──────────────────────────────────────────────────────────────────────────

    async def get_best_strategy(
        self,
        user_id: str,
        event_type: str,
        archetype: Optional[str] = None,
    ) -> Optional[ProceduralMemory]:
        """
        Find the highest-success-rate strategy matching event_type and archetype.

        Matching priority:
          1. event_type match + archetype match → highest success_rate
          2. event_type match only (archetype = None) → highest success_rate
          3. Any strategy → highest success_rate (last resort)

        Args:
            user_id: User to match strategies for.
            event_type: Triggering event type (e.g., "OVERSPEND").
            archetype: User behavioral archetype (optional).

        Returns:
            Best-matching ProceduralMemory, or None if database is empty.

        Example:
            >>> s = await store.get_best_strategy("user-1", "OVERSPEND", "impulse_spender_reward_driven")
            >>> s.strategy_id
            'soft_nudge_positive_frame'
        """
        # Attempt 1: event_type + exact archetype match
        if archetype:
            filters = [
                {"user_id": user_id, "trigger_condition.event_type": event_type,
                 "user_condition.archetype": archetype},
                {"user_id": user_id, "trigger_condition.event_type": event_type,
                 "user_condition": None},
            ]
        else:
            filters = [
                {"user_id": user_id, "trigger_condition.event_type": event_type},
            ]

        for flt in filters:
            try:
                cursor = self._col.find(flt).sort("success_rate", -1).limit(1)
                docs   = await cursor.to_list(length=1)
                if docs:
                    return _doc_to_procedural(docs[0])
            except Exception as exc:
                logger.warning(f"[PROCEDURAL] Strategy query failed: {exc}")

        # Fallback: any strategy for this user, highest success rate
        try:
            cursor = self._col.find({"user_id": user_id}).sort("success_rate", -1).limit(1)
            docs   = await cursor.to_list(length=1)
            return _doc_to_procedural(docs[0]) if docs else None
        except Exception:
            return None

    async def retrieve(
        self,
        user_id: str,
        event_type: Optional[str] = None,
        archetype: Optional[str] = None,
        limit: int = 3,
        query_embedding: Optional[object] = None,
    ) -> List[ProceduralMemory]:
        """
        Retrieve top N matching strategies — backward-compatible interface.

        Args:
            user_id: User identifier.
            event_type: Optional event type filter.
            archetype: Optional archetype filter.
            limit: Max strategies to return.
            query_embedding: Ignored (interface compatibility).

        Returns:
            List of ProceduralMemory sorted by success_rate DESC.

        Example:
            >>> strategies = await store.retrieve("user-1", "OVERSPEND")
        """
        flt: dict = {"user_id": user_id}
        if event_type:
            flt["trigger_condition.event_type"] = event_type
        try:
            cursor = self._col.find(flt).sort("success_rate", -1).limit(limit)
            docs   = await cursor.to_list(length=limit)
            return [_doc_to_procedural(d) for d in docs]
        except Exception as exc:
            logger.warning(f"[PROCEDURAL] Retrieve failed: {exc}")
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # UPDATES
    # ──────────────────────────────────────────────────────────────────────────

    async def update_outcome(
        self,
        strategy_id: str,
        user_id: str,
        success: bool,
    ) -> None:
        """
        Apply EMA update to a strategy's success rate.

        Formula:
          outcome_val = 1.0 if success else 0.0
          new_rate = EMA_ALPHA * outcome_val + (1 - EMA_ALPHA) * current_rate

        Args:
            strategy_id: Strategy to update.
            user_id: Owner user (safety filter).
            success: True if the strategy produced a positive user reaction.

        Example:
            >>> await store.update_outcome("soft_nudge_positive_frame", "user-1", success=True)
        """
        outcome_val = 1.0 if success else 0.0
        now         = datetime.utcnow()

        # MongoDB aggregation pipeline update for EMA
        ema_pipeline = [
            {
                "$set": {
                    "success_rate": {
                        "$add": [
                            {"$multiply": [_EMA_ALPHA, outcome_val]},
                            {"$multiply": [1 - _EMA_ALPHA, "$success_rate"]},
                        ]
                    },
                    "success_count": {
                        "$cond": [success, {"$add": ["$success_count", 1]}, "$success_count"]
                    },
                    "failure_count": {
                        "$cond": [not success, {"$add": ["$failure_count", 1]}, "$failure_count"]
                    },
                    "last_applied" : now,
                    "last_outcome" : "success" if success else "failure",
                    "updated_at"   : now,
                }
            }
        ]

        try:
            await self._col.update_one(
                {"strategy_id": strategy_id, "user_id": user_id},
                ema_pipeline,
            )
        except Exception as exc:
            logger.warning(f"[PROCEDURAL] Outcome update failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _doc_to_procedural(doc: dict) -> ProceduralMemory:
    """Convert Atlas document to ProceduralMemory Pydantic model."""
    return ProceduralMemory(
        id                = doc.get("id", str(doc.get("_id", ""))),
        user_id           = doc["user_id"],
        strategy_id       = doc.get("strategy_id", ""),
        trigger_condition = doc.get("trigger_condition", {}),
        user_condition    = doc.get("user_condition"),
        action_template   = doc.get("action_template", ""),
        tone_override     = doc.get("tone_override"),
        success_count     = int(doc.get("success_count", 0)),
        failure_count     = int(doc.get("failure_count", 0)),
        success_rate      = float(doc.get("success_rate", 0.5)),
        last_applied      = doc.get("last_applied"),
        last_outcome      = doc.get("last_outcome"),
        created_at        = doc.get("created_at", datetime.utcnow()),
        updated_at        = doc.get("updated_at", datetime.utcnow()),
    )
