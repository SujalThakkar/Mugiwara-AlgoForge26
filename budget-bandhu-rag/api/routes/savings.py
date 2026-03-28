"""
Savings Routes — Gross Savings Panel Data
Computes personal gross savings from two streams:
  Stream A: Forecast savings (ML predicted spend - actual spend)
  Stream B: Hard savings (salary - actual spend from CSV uploads)

Author: Budget Bandhu Goals 2.0
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/savings", tags=["Savings"])


async def _compute_gross_savings(user_id: str, db) -> dict:
    """
    Compute gross savings for a user. Shared helper used by:
      - GET /api/v1/savings/{user_id}  (Savings Panel)
      - GET /api/v1/escrow/{pool_id}   (member saved_amount in Group Goal Panel)

    Returns:
        {
            "hard_savings": float,
            "forecast_savings": float,
            "gross_savings": float,
            "forecast_source": "ml" | "average" | "none",
            "period": "monthly",
        }
    """
    # ── Stream B: Hard Savings ────────────────────────────────────────────────
    # Sum "current" from all goals with salary mode (salary is set)
    hard_savings = 0.0
    salary_goals = await db["goals"].find({
        "user_id": user_id,
        "salary": {"$exists": True, "$ne": None},
    }).to_list(length=50)

    for goal in salary_goals:
        hard_savings += goal.get("current", 0)

    # ── Stream A: Forecast Savings ────────────────────────────────────────────
    # Try ML forecast first, fallback to average of past CSV upload periods
    forecast_savings = 0.0
    forecast_source = "none"

    try:
        from intelligence.ml_client import get_forecast
        forecast_data = await get_forecast(user_id)
        # forecast_data should contain predicted_spend for the period
        predicted_spend = forecast_data.get("predicted_spend", 0)

        # Get actual spend from recent transactions
        cutoff = datetime.utcnow() - timedelta(days=30)
        pipeline = [
            {"$match": {
                "user_id": user_id,
                "type": "debit",
                "created_at": {"$gte": cutoff},
            }},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
        result = await db["transactions"].aggregate(pipeline).to_list(length=1)
        actual_spend = result[0]["total"] if result else 0

        forecast_savings = max(0.0, predicted_spend - actual_spend)
        forecast_source = "ml"
    except Exception:
        # ML service unavailable — fallback to average savings from past goals
        # that used forecast mode (no salary)
        try:
            forecast_goals = await db["goals"].find({
                "user_id": user_id,
                "$or": [
                    {"salary": None},
                    {"salary": {"$exists": False}},
                ],
                "current": {"$gt": 0},
            }).to_list(length=20)

            if forecast_goals:
                total = sum(g.get("current", 0) for g in forecast_goals)
                forecast_savings = round(total / len(forecast_goals), 2)
                forecast_source = "average"
        except Exception:
            pass

    gross_savings = round(hard_savings + forecast_savings, 2)

    return {
        "hard_savings": round(hard_savings, 2),
        "forecast_savings": round(forecast_savings, 2),
        "gross_savings": gross_savings,
        "forecast_source": forecast_source,
        "period": "monthly",
    }


@router.get("/{user_id}")
async def get_savings(user_id: str, db=Depends(get_database)):
    """
    Get gross savings panel data for a user.
    Returns hard savings (salary - spend) + forecast savings (predicted - actual).
    """
    try:
        data = await _compute_gross_savings(user_id, db)
        return {
            "user_id": user_id,
            **data,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"[Savings] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
