"""
Dashboard Routes - Unified Dashboard Data
Aggregates data from multiple sources for the main dashboard.
Includes LSTM forecast with 6-hour MongoDB caching.

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from api.database import get_database
from intelligence.ml_client import forecast_from_transactions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

FORECAST_CACHE_TTL_HOURS = 6


async def _get_cached_forecast(db, user_id: str) -> Optional[dict]:
    """Return cached forecast if not expired, else None."""
    entry = await db["forecast_cache"].find_one({"user_id": user_id})
    if entry and entry.get("expires_at") and entry["expires_at"] > datetime.utcnow():
        return entry.get("forecast")
    return None


async def _set_cached_forecast(db, user_id: str, forecast: dict):
    """Upsert forecast cache with TTL."""
    await db["forecast_cache"].update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "forecast": forecast,
            "computed_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=FORECAST_CACHE_TTL_HOURS),
        }},
        upsert=True,
    )


@router.get("/{user_id}")
async def get_dashboard(user_id: str, db=Depends(get_database)):
    """
    Get comprehensive dashboard data for a user.
    Aggregates: user info, stats, category breakdown, insights, LSTM forecast, etc.
    """
    try:
        # 1. Get or auto-create user
        user = await db["users"].find_one({"_id": user_id})
        if not user:
            # Auto-create a lightweight user record on first dashboard access
            user = {"_id": user_id, "name": "User", "income": 50000, "created_at": datetime.utcnow()}
            await db["users"].insert_one(user)

        # 2. Get transactions (last 30 days) - Query by actual transaction date
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "date": {"$gte": thirty_days_ago}
        }).sort("date", -1)
        transactions = await txn_cursor.to_list(length=1000)

        # 3. Calculate stats — use actual credits, not assumed income
        total_debit  = round(sum(t.get("amount", 0) for t in transactions if t.get("type") == "debit"), 2)
        total_credit = round(sum(t.get("amount", 0) for t in transactions if t.get("type") == "credit"), 2)
        income = user.get("income", 50000)
        # If no credit transactions yet, fall back to income as baseline
        effective_credit = total_credit if total_credit > 0 else income

        # 4. Category breakdown
        category_breakdown = {}
        for txn in transactions:
            if txn.get("type") == "debit":
                cat = txn.get("category", "Other")
                if cat not in category_breakdown:
                    category_breakdown[cat] = {"total": 0, "count": 0}
                category_breakdown[cat]["total"] += txn.get("amount", 0)
                category_breakdown[cat]["count"] += 1

        # 5. Anomalies
        anomalies = [t for t in transactions if t.get("is_anomaly")]

        # 6. Generate insights
        insights = []
        for cat, data in category_breakdown.items():
            pct = (data["total"] / total_debit * 100) if total_debit > 0 else 0
            if pct > 30:
                insights.append({
                    "type": "high_spending",
                    "title": f"High {cat} Spending",
                    "description": f"You've spent ₹{data['total']:,.0f} on {cat} this month ({pct:.0f}%)",
                    "severity": "warning",
                    "icon": "alert-triangle"
                })

        if total_credit > total_debit:
            insights.append({
                "type": "positive_cashflow",
                "title": "Positive Cash Flow",
                "description": "Great job! You're earning more than spending.",
                "severity": "success",
                "icon": "trending-up"
            })

        # 7. Budget summary — live aggregation via $group so spent is always accurate
        budget = await db["budgets"].find_one({"user_id": user_id})

        # Aggregate actual spending per category this month from transactions
        agg_pipeline = [
            {"$match": {"user_id": user_id, "type": "debit", "date": {"$gte": thirty_days_ago}}},
            {"$group": {"_id": "$category", "total_spent": {"$sum": "$amount"}}}
        ]
        agg_result = await db["transactions"].aggregate(agg_pipeline).to_list(length=100)
        live_spend_by_cat = {r["_id"]: round(r["total_spent"], 2) for r in agg_result}

        budget_summary = None
        if budget:
            # Merge live spend into stored allocations
            merged_allocs = []
            for a in budget.get("allocations", []):
                cat = a.get("category", "Other")
                merged_allocs.append({
                    "category": cat,
                    "allocated": a.get("allocated", 0),
                    "spent": live_spend_by_cat.get(cat, 0)
                })
            total_allocated = sum(a["allocated"] for a in merged_allocs)
            total_spent_budget = sum(a["spent"] for a in merged_allocs)
            budget_summary = {
                "total_allocated": total_allocated,
                "total_spent": total_spent_budget,
                "allocations": merged_allocs
            }
        else:
            # Synthesize from category breakdown if no budget set
            synth_allocs = [
                {"category": cat, "spent": round(data["total"], 2), "allocated": round(income / 4, 0)}
                for cat, data in list(category_breakdown.items())[:6]
            ]
            budget_summary = {
                "total_allocated": income,
                "total_spent": total_debit,
                "allocations": synth_allocs
            }

        # 8. Goals summary
        goals_cursor = db["goals"].find({"user_id": user_id})
        goals = await goals_cursor.to_list(length=20)
        goals_summary = {
            "total": len(goals),
            "total_saved": sum(g.get("current", 0) for g in goals),
            "total_target": sum(g.get("target", 0) for g in goals)
        }

        # 9. LSTM Forecast (with 6-hour cache)
        forecast_data = None
        try:
            forecast_data = await _get_cached_forecast(db, user_id)
            if forecast_data is None:
                # Fetch last 90 days for forecaster - Query by date
                ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
                forecast_txn_cursor = db["transactions"].find({
                    "user_id": user_id,
                    "date": {"$gte": ninety_days_ago}
                })
                forecast_txns = await forecast_txn_cursor.to_list(length=2000)

                if len(forecast_txns) >= 3:  # Lower threshold for demoing trend
                    # Serialize for ML service
                    serialized = []
                    for t in forecast_txns:
                        d = t.get("date") or t.get("created_at", datetime.utcnow())
                        if isinstance(d, datetime):
                            d = d.strftime("%Y-%m-%d")
                        serialized.append({
                            "date": str(d)[:10],
                            "amount": t.get("amount", 0),
                            "category": t.get("category", "Other"),
                            "type": t.get("type", "debit"),
                        })

                    forecast_data = await forecast_from_transactions(user_id, serialized, income)
                    await _set_cached_forecast(db, user_id, forecast_data)
        except Exception as e:
            logger.warning(f"[Dashboard] Forecast failed (graceful fallback): {e}")
            forecast_data = {}

        if forecast_data is None:
            forecast_data = {}

        return {
            "user": {
                "id": user_id,
                "name": user.get("name", "User"),
                "income": income
            },
            "stats": {
                "current_balance": round(total_credit - total_debit, 2),
                "month_spent": total_debit,
                "month_income": total_credit if total_credit > 0 else income,
                "month_saved": round(effective_credit - total_debit, 2),
                "savings_rate": round(max(0.0, min(100.0, (effective_credit - total_debit) / max(1, effective_credit) * 100)), 2),
                "financial_score": round(max(20, min(100, 60 + (max(0, (effective_credit - total_debit) / max(1, effective_credit) * 100)) / 2)), 0),
                "total_transactions": len(transactions)
            },
            "category_breakdown": {
                cat: {"total": round(val["total"], 2), "count": val["count"]}
                for cat, val in category_breakdown.items()
            },
            "anomalies": {
                "count": len(anomalies),
                "rate": round((len(anomalies) / len(transactions) * 100), 2) if transactions else 0
            },
            "insights": insights,
            "forecast": forecast_data,
            "budget_summary": budget_summary,
            "goals_summary": goals_summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Dashboard] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/spending-trend")
async def get_spending_trend(user_id: str, days: int = 30, db=Depends(get_database)):
    """Get daily spending trend for the specified period"""
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "type": "debit",
            "date": {"$gte": start_date}
        }).sort("date", 1)

        transactions = await txn_cursor.to_list(length=1000)

        # Group by date
        daily_totals = {}
        for txn in transactions:
            date_key = txn.get("date", txn.get("created_at", datetime.utcnow()))
            if isinstance(date_key, datetime):
                date_str = date_key.strftime("%Y-%m-%d")
            else:
                date_str = str(date_key)[:10]

            if date_str not in daily_totals:
                daily_totals[date_str] = 0
            daily_totals[date_str] += txn.get("amount", 0)

        # Convert to list
        trend = [{"date": date, "amount": amount} for date, amount in sorted(daily_totals.items())]

        return trend

    except Exception as e:
        logger.error(f"[SpendingTrend] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
