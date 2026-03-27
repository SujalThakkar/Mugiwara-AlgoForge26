"""
Insights/Analytics Routes
BudgetBandhu API
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from api.database import get_database

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

def generate_insights(user_id: str, transactions: List[Dict]) -> Dict:
    category_totals = {}
    total_spend = 0
    for txn in transactions:
        category = txn.get('category', 'Other')
        amount = abs(txn.get('amount', 0))
        category_totals[category] = category_totals.get(category, 0) + amount
        total_spend += amount
    
    insights = []
    for category, amount in category_totals.items():
        percentage = (amount / total_spend * 100) if total_spend > 0 else 0
        if percentage > 25:
            insights.append({
                'type': 'overspend',
                'category': category,
                'amount': round(amount, 2),
                'percentage': round(percentage, 1),
                'message': f'High spending in {category}: ₹{amount:,.0f} ({percentage:.1f}%)'
            })
            
    recs = []
    for insight in insights:
        if insight['type'] == 'overspend':
            recs.append(f"💡 Reduce {insight['category']} by 10-15%")
    if not recs:
        recs.append("✅ Your spending looks balanced!")
        
    return {
        'insights': insights,
        'total_spend': round(total_spend, 2),
        'category_breakdown': {k: round(v, 2) for k, v in category_totals.items()},
        'recommendations': recs
    }

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
            
        result = generate_insights(user_id, txns)
        return {"success": True, **result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
