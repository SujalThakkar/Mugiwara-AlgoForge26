"""
Dashboard Routes - Unified Dashboard Data
Aggregates data from multiple sources for the main dashboard

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/{user_id}")
async def get_dashboard(user_id: str, db=Depends(get_database)):
    """
    Get comprehensive dashboard data for a user.
    Aggregates: user info, stats, category breakdown, insights, etc.
    """
    try:
        # 1. Get user
        user = await db["users"].find_one({"_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # 2. Get transactions (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "created_at": {"$gte": thirty_days_ago}
        }).sort("created_at", -1)
        transactions = await txn_cursor.to_list(length=500)
        
        # 3. Calculate stats
        total_debit = sum(t.get("amount", 0) for t in transactions if t.get("type") == "debit")
        total_credit = sum(t.get("amount", 0) for t in transactions if t.get("type") == "credit")
        income = user.get("income", 50000)
        
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
        
        # 7. Budget summary
        budget = await db["budgets"].find_one({"user_id": user_id})
        budget_summary = None
        if budget:
            total_allocated = sum(a.get("allocated", 0) for a in budget.get("allocations", []))
            total_spent = sum(a.get("spent", 0) for a in budget.get("allocations", []))
            budget_summary = {
                "total_allocated": total_allocated,
                "total_spent": total_spent
            }
        
        # 8. Goals summary
        goals_cursor = db["goals"].find({"user_id": user_id})
        goals = await goals_cursor.to_list(length=20)
        goals_summary = {
            "total": len(goals),
            "total_saved": sum(g.get("current", 0) for g in goals),
            "total_target": sum(g.get("target", 0) for g in goals)
        }
        
        return {
            "user": {
                "id": user_id,
                "name": user.get("name", "User"),
                "income": income
            },
            "stats": {
                "current_balance": income - total_debit + total_credit,
                "month_spent": total_debit,
                "month_saved": income - total_debit,
                "savings_rate": ((income - total_debit) / income * 100) if income > 0 else 0,
                "financial_score": min(100, max(0, 50 + (income - total_debit) / 1000)),
                "total_transactions": len(transactions)
            },
            "category_breakdown": category_breakdown,
            "anomalies": {
                "count": len(anomalies),
                "rate": (len(anomalies) / len(transactions) * 100) if transactions else 0
            },
            "insights": insights,
            "forecast": None,  # TODO: Integrate with forecaster
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
        start_date = datetime.utcnow() - timedelta(days=days)
        
        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "type": "debit",
            "created_at": {"$gte": start_date}
        }).sort("created_at", 1)
        
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
