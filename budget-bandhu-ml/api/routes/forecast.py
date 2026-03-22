"""
Forecast Routes
BudgetBandhu API
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from api.database import get_database
from intelligence.tanuj_integration import get_tanuj_service

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecast"])
tanuj_ml = get_tanuj_service()

class ForecastRequest(BaseModel):
    user_id: str
    months: int = 3

@router.post("", response_model=dict)
async def forecast_expenses(request: ForecastRequest, db=Depends(get_database)):
    """
    Forecast future expenses based on history.
    """
    try:
        # Fetch history from Mongo
        # transactions collection
        cursor = db["transactions"].find(
            {"user_id": request.user_id, "type": "debit"}
        ).sort("date", -1).limit(100)
        
        history = []
        async for doc in cursor:
            history.append({
                "amount": doc["amount"],
                "date": doc["created_at"] if isinstance(doc.get("date"), str) else doc["date"] # Handle format variance
            })
            
        result = tanuj_ml.forecast_expenses(request.user_id, history, request.months)
        return {"success": True, **result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
