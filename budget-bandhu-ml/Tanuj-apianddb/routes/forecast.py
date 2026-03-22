"""
Forecast Routes - LSTM Spending Predictions
BudgetBandhu API

Provides spending forecasts using trained LSTM model.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from api.database import get_database
from intelligence.forecaster import LSTMSavingsForecaster

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecast"])

# Initialize LSTM forecaster (singleton)
print("[FORECAST] Loading LSTM forecaster...")
forecaster = LSTMSavingsForecaster("models/lstm_forecaster/model.pth")
print("[FORECAST] Forecaster ready")


class ForecastRequest(BaseModel):
    user_id: str
    horizon: str = "30d"  # 7d, 30d, or 90d
    current_balance: Optional[float] = 0


class ForecastResponse(BaseModel):
    user_id: str
    horizon: str
    predicted_spending: List[float]
    predicted_savings: float
    daily_average: float
    confidence: float
    trend: str
    method: str


@router.get("/{user_id}")
async def get_forecast(
    user_id: str,
    horizon: str = "30d",
    db=Depends(get_database)
):
    """
    Get spending forecast for a user.
    Uses their historical transaction data to predict future spending.
    
    Returns:
        - predicted_spending: Daily spending predictions
        - predicted_savings: Projected savings based on current balance
        - confidence: Model confidence (0-1)
        - trend: 'increasing', 'decreasing', or 'stable'
    """
    # Fetch user's transaction history
    try:
        cursor = db["transactions"].find(
            {"user_id": user_id, "type": "debit"},
            {"amount": 1, "date": 1}
        ).sort("date", -1).limit(90)  # Last 90 transactions
        
        transactions = await cursor.to_list(length=90)
    except Exception as e:
        print(f"[FORECAST] DB error: {e}")
        transactions = []
    
    if len(transactions) < 7:
        # Not enough data - return mock forecast
        return {
            "user_id": user_id,
            "horizon": horizon,
            "predicted_spending": [1500] * (7 if horizon == "7d" else 30 if horizon == "30d" else 90),
            "predicted_savings": 0,
            "daily_average": 1500,
            "confidence": 0.3,
            "trend": "stable",
            "method": "fallback",
            "message": "Not enough transaction history for accurate forecast"
        }
    
    # Extract spending amounts (most recent first, so reverse)
    historical_spending = [t["amount"] for t in reversed(transactions)]
    
    # Get user's current balance
    try:
        user = await db["users"].find_one({"_id": user_id})
        current_balance = user.get("income", 50000) if user else 50000
    except:
        current_balance = 50000
    
    # Run forecast
    result = forecaster.process({
        "historical_spending": historical_spending,
        "horizon": horizon,
        "current_balance": current_balance
    })
    
    forecast = result["result"]
    
    return {
        "user_id": user_id,
        "horizon": horizon,
        "predicted_spending": forecast["predicted_spending"],
        "predicted_savings": forecast.get("predicted_savings", 0),
        "daily_average": forecast["forecast_mean"],
        "confidence": forecast["confidence"],
        "trend": forecast.get("trend", "stable"),
        "method": forecast.get("method", "lstm")
    }


@router.post("")
async def create_forecast(
    request: ForecastRequest,
    db=Depends(get_database)
):
    """
    Create a forecast with custom parameters.
    """
    return await get_forecast(
        user_id=request.user_id,
        horizon=request.horizon,
        db=db
    )


@router.get("/{user_id}/summary")
async def get_forecast_summary(
    user_id: str,
    db=Depends(get_database)
):
    """
    Get a simplified forecast summary for dashboard.
    Returns single predicted_savings value for 30-day horizon.
    """
    result = await get_forecast(user_id, "30d", db)
    
    return {
        "horizon": "30d",
        "predicted_savings": result["predicted_savings"],
        "confidence": result["confidence"]
    }
