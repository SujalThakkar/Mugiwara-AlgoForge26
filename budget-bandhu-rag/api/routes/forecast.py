"""
Forecast Routes
BudgetBandhu API
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from api.database import get_database
from intelligence.ml_client import get_forecast

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecast"])

class ForecastRequest(BaseModel):
    user_id: str
    months: int = 3

@router.post("", response_model=dict)
async def forecast_expenses(request: ForecastRequest, db=Depends(get_database)):
    """
    Forecast future expenses based on history via microservice.
    """
    try:
        # The external model server handles fetching and orchestrating models
        result = await get_forecast(request.user_id)
        return {"success": True, **result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
