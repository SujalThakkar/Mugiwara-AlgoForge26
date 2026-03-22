"""
Dashboard Routes - Aggregated Stats + InsightsGenerator
BudgetBandhu API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timedelta
from bson import ObjectId

from api.database import get_database
from intelligence.forecaster import LSTMSavingsForecaster
import numpy as np

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

# Initialize LSTM Forecaster
print("[DASHBOARD] Loading LSTM Forecaster...")
try:
    forecaster = LSTMSavingsForecaster(model_path="models/lstm_forecaster/model.pth")
    FORECASTER_AVAILABLE = True
except Exception as e:
    print(f"[DASHBOARD] LSTM not loaded: {e}")
    FORECASTER_AVAILABLE = False


@router.get("/{user_id}")
async def get_dashboard(user_id: str, db=Depends(get_database)):
    """
    Get complete dashboard data with ML-powered insights.
    
    Returns:
    - Balance & spending stats
    - Category breakdown (from Categorizer)
    - Anomaly summary
    - Financial health score (from InsightsGenerator logic)
    - Savings forecast (from LSTMForecaster)
    """
    # Get user
    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    income = user["income"]
    
    # Get current month's transactions
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    
    # Aggregate spending by category
    pipeline = [
        {"$match": {"user_id": user_id, "type": "debit", "created_at": {"$gte": start_of_month}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    category_breakdown_raw = await db["transactions"].aggregate(pipeline).to_list(100)
    category_breakdown = {item["_id"]: {"total": item["total"], "count": item["count"]} for item in category_breakdown_raw}
    
    # Total spent this month
    total_spent = sum(item["total"] for item in category_breakdown_raw)
    
    # Total income (credits) this month
    income_pipeline = [
        {"$match": {"user_id": user_id, "type": "credit", "created_at": {"$gte": start_of_month}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    income_result = await db["transactions"].aggregate(income_pipeline).to_list(1)
    total_income_received = income_result[0]["total"] if income_result else 0
    
    # Monthly savings
    month_saved = total_income_received - total_spent if total_income_received > total_spent else 0
    savings_rate = month_saved / total_income_received if total_income_received > 0 else 0
    
    # Anomaly stats
    anomaly_count = await db["transactions"].count_documents({
        "user_id": user_id,
        "is_anomaly": True,
        "created_at": {"$gte": start_of_month}
    })
    total_txn_count = await db["transactions"].count_documents({
        "user_id": user_id,
        "created_at": {"$gte": start_of_month}
    })
    anomaly_rate = anomaly_count / total_txn_count if total_txn_count > 0 else 0
    
    # Financial Health Score (InsightsGenerator logic)
    # score = 800 - (total_spent/10000 × 100) - (anomaly_rate × 200)
    financial_score = 800 - (total_spent / 10000 * 100) - (anomaly_rate * 200)
    financial_score = max(300, min(900, financial_score))  # Clamp 300-900
    
    # Generate insights
    insights = generate_insights(category_breakdown, total_spent, income, savings_rate, anomaly_count)
    
    # Get budget data
    budget = await db["budgets"].find_one({"user_id": user_id})
    
    # Savings forecast (if LSTM available)
    forecast = None
    if FORECASTER_AVAILABLE:
        try:
            # Get last 30 days of spending
            thirty_days_ago = now - timedelta(days=30)
            spending_cursor = db["transactions"].find({
                "user_id": user_id,
                "type": "debit",
                "created_at": {"$gte": thirty_days_ago}
            }).sort("created_at", 1)
            spending_list = await spending_cursor.to_list(100)
            
            if len(spending_list) >= 7:
                daily_spending = [txn["amount"] for txn in spending_list]
                forecast_result = forecaster.process({
                    "historical_spending": daily_spending,
                    "horizon": "30d"
                })
                forecast = {
                    "horizon": "30d",
                    "predicted_savings": round(income - sum(forecast_result["result"]["predicted_spending"][:30]) / 30, 0),
                    "confidence": 0.85
                }
        except Exception as e:
            print(f"[DASHBOARD] Forecast error: {e}")
    
    # Goals summary
    goals = await db["goals"].find({"user_id": user_id}).to_list(10)
    goals_summary = {
        "total": len(goals),
        "total_saved": sum(g.get("current", 0) for g in goals),
        "total_target": sum(g.get("target", 0) for g in goals)
    }
    
    return {
        "user": {
            "id": user_id,
            "name": user["name"],
            "income": income
        },
        "stats": {
            "current_balance": total_income_received - total_spent,
            "month_spent": round(total_spent, 2),
            "month_saved": round(month_saved, 2),
            "savings_rate": round(savings_rate * 100, 1),
            "financial_score": round(financial_score),
            "total_transactions": total_txn_count
        },
        "category_breakdown": category_breakdown,
        "anomalies": {
            "count": anomaly_count,
            "rate": round(anomaly_rate * 100, 1)
        },
        "insights": insights,
        "forecast": forecast,
        "budget_summary": {
            "total_allocated": sum(a["allocated"] for a in budget["allocations"]) if budget else 0,
            "total_spent": sum(a["spent"] for a in budget["allocations"]) if budget else 0
        } if budget else None,
        "goals_summary": goals_summary
    }


def generate_insights(category_breakdown: dict, total_spent: float, income: float, savings_rate: float, anomaly_count: int) -> list:
    """Generate insights based on spending patterns"""
    insights = []
    
    # Find top spending category
    if category_breakdown:
        top_category = max(category_breakdown.items(), key=lambda x: x[1]["total"])
        insights.append({
            "type": "top_spending",
            "title": f"Highest spending: {top_category[0]}",
            "description": f"You spent ₹{top_category[1]['total']:,.0f} on {top_category[0]} this month.",
            "severity": "info",
            "icon": "📊"
        })
    
    # Savings rate insight
    if savings_rate >= 0.3:
        insights.append({
            "type": "achievement",
            "title": "Great Savings Rate! 🎉",
            "description": f"You're saving {savings_rate*100:.0f}% of your income. Keep it up!",
            "severity": "success",
            "icon": "💰"
        })
    elif savings_rate < 0.1:
        insights.append({
            "type": "warning",
            "title": "Low Savings Alert",
            "description": f"Your savings rate is only {savings_rate*100:.0f}%. Try to save at least 20%.",
            "severity": "warning",
            "icon": "⚠️"
        })
    
    # Anomaly insight
    if anomaly_count > 0:
        insights.append({
            "type": "anomaly",
            "title": f"{anomaly_count} Unusual Transaction{'s' if anomaly_count > 1 else ''} Detected",
            "description": "Review your transactions for suspicious activity.",
            "severity": "warning",
            "icon": "🔍"
        })
    
    # Budget adherence
    if total_spent / income > 0.8:
        insights.append({
            "type": "budget_alert",
            "title": "High Spending Month",
            "description": f"You've spent {(total_spent/income)*100:.0f}% of your income already.",
            "severity": "warning",
            "icon": "📈"
        })
    
    return insights


@router.get("/{user_id}/spending-trend")
async def get_spending_trend(user_id: str, days: int = 30, db=Depends(get_database)):
    """Get daily spending trend for charts"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    pipeline = [
        {"$match": {
            "user_id": user_id,
            "type": "debit",
            "created_at": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    daily_spending = await db["transactions"].aggregate(pipeline).to_list(days)
    
    # Fill missing days with 0
    result = []
    for i in range(days):
        date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        amount = next((d["total"] for d in daily_spending if d["_id"] == date), 0)
        result.append({"date": date, "amount": amount})
    
    return result
