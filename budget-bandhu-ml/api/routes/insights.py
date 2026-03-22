"""
Insights/Analytics Routes
BudgetBandhu API
"""
from fastapi import APIRouter, Depends, HTTPException
from api.database import get_database
from intelligence.tanuj_integration import get_tanuj_service

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])
tanuj_ml = get_tanuj_service()

@router.get("/{user_id}", response_model=dict)
async def get_analytics(user_id: str, db=Depends(get_database)):
    """
    Get spending insights for a user.
    """
    try:
        cursor = db["transactions"].find(
            {"user_id": user_id, "type": "debit"}
        ).limit(200)
        
        txns = []
        async for doc in cursor:
            txns.append({
                "amount": doc["amount"],
                "category": doc.get("category", "Other"),
                "description": doc["description"]
            })
            
        result = tanuj_ml.generate_insights(user_id, txns)
        return {"success": True, **result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
