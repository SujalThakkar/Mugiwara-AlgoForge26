"""
Budget Routes - CRUD + PolicyLearner Recommendations
BudgetBandhu API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime
from bson import ObjectId

from api.database import get_database
from api.models.budget import (
    Budget, BudgetCreate, BudgetAllocation, 
    BudgetRecommendation, BudgetRecommendationResponse,
    generate_default_budget
)
from intelligence.policy_learner import PolicyLearner

router = APIRouter(prefix="/api/v1/budget", tags=["Budget"])

# Initialize PolicyLearner
print("[BUDGET] Loading PolicyLearner...")
try:
    policy_learner = PolicyLearner(q_table_path="models/q_learning/q_table.npy")
    POLICY_LEARNER_AVAILABLE = True
except Exception as e:
    print(f"[BUDGET] PolicyLearner not loaded: {e}")
    policy_learner = PolicyLearner()  # Fresh instance
    POLICY_LEARNER_AVAILABLE = True  # Works without pre-trained Q-table


@router.get("/{user_id}")
async def get_budget(user_id: str, db=Depends(get_database)):
    """Get user's budget allocations"""
    budget = await db["budgets"].find_one({"user_id": user_id})
    
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found. Create one first.")
    
    budget["id"] = str(budget.pop("_id"))
    return budget


@router.put("/{user_id}")
async def update_budget(user_id: str, budget_data: BudgetCreate, db=Depends(get_database)):
    """Update user's budget allocations (manual edit from UI)"""
    
    # Validate allocations don't exceed income
    total_allocated = sum(a.allocated for a in budget_data.allocations)
    if total_allocated > budget_data.total_income:
        raise HTTPException(
            status_code=400, 
            detail=f"Total allocations (₹{total_allocated}) exceed income (₹{budget_data.total_income})"
        )
    
    update_doc = {
        "total_income": budget_data.total_income,
        "allocations": [a.model_dump() for a in budget_data.allocations],
        "updated_at": datetime.utcnow()
    }
    
    result = await db["budgets"].update_one(
        {"user_id": user_id},
        {"$set": update_doc}
    )
    
    if result.matched_count == 0:
        # Create new budget if doesn't exist
        update_doc["user_id"] = user_id
        update_doc["savings_target"] = budget_data.total_income * 0.20
        update_doc["current_savings"] = 0.0
        update_doc["created_at"] = datetime.utcnow()
        await db["budgets"].insert_one(update_doc)
    
    print(f"[BUDGET] Updated for user {user_id}")
    return {"message": "Budget updated", "total_allocated": total_allocated}


@router.get("/{user_id}/recommend", response_model=BudgetRecommendationResponse)
async def get_budget_recommendations(user_id: str, db=Depends(get_database)):
    """
    Get AI budget recommendations from PolicyLearner.
    
    Analyzes actual spending vs allocations and suggests adjustments.
    """
    # Get current budget
    budget = await db["budgets"].find_one({"user_id": user_id})
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    
    # Get user income
    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    income = user["income"]
    
    # Aggregate actual spending by category (current month)
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    
    pipeline = [
        {"$match": {"user_id": user_id, "type": "debit", "created_at": {"$gte": start_of_month}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
    ]
    spending_raw = await db["transactions"].aggregate(pipeline).to_list(100)
    historical_spending = {item["_id"]: item["total"] for item in spending_raw}
    
    # Build current budget dict
    current_budget = {a["category"]: a["allocated"] for a in budget["allocations"]}
    
    # Run PolicyLearner
    policy_result = policy_learner.process({
        "historical_spending": historical_spending,
        "income": income
    })
    
    # Generate recommendations
    recommendations = []
    total_savings_potential = 0
    
    for category, data in policy_result["result"].items():
        current_alloc = current_budget.get(category, 0)
        actual_spent = historical_spending.get(category, 0)
        recommended = data["recommended"]
        
        # Determine change direction
        if recommended > current_alloc * 1.05:
            change = "increase"
            reason = f"Consistently spending ₹{actual_spent:,.0f} vs allocated ₹{current_alloc:,.0f}"
        elif recommended < current_alloc * 0.95:
            change = "decrease"
            savings = current_alloc - recommended
            total_savings_potential += savings
            reason = f"Underspending by ₹{current_alloc - actual_spent:,.0f}. Reallocate to savings."
        else:
            change = "maintain"
            reason = "Spending aligns with allocation."
        
        recommendations.append(BudgetRecommendation(
            category=category,
            current_allocation=current_alloc,
            actual_spent=actual_spent,
            recommended=recommended,
            multiplier=data["multiplier"],
            change=change,
            reason=reason
        ))
    
    # Sort by absolute difference (most impactful first)
    recommendations.sort(key=lambda r: abs(r.recommended - r.current_allocation), reverse=True)
    
    return BudgetRecommendationResponse(
        user_id=user_id,
        recommendations=recommendations,
        total_savings_potential=total_savings_potential,
        method="policy_learning"
    )


@router.post("/{user_id}/feedback")
async def submit_budget_feedback(
    user_id: str,
    category: str,
    feedback: str,  # "accepted" or "rejected"
    db=Depends(get_database)
):
    """
    Submit feedback on a recommendation.
    Updates PolicyLearner to improve future recommendations.
    """
    if feedback not in ["accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Feedback must be 'accepted' or 'rejected'")
    
    # Update PolicyLearner
    policy_learner.update_policy(category, feedback)
    
    print(f"[BUDGET] Feedback: {category} → {feedback}")
    
    return {
        "message": f"Feedback recorded for {category}",
        "feedback": feedback,
        "policy_updated": True
    }


@router.post("/{user_id}/reset")
async def reset_budget_to_default(user_id: str, db=Depends(get_database)):
    """Reset budget to default 50/30/20 allocations based on income"""
    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    default_allocations = generate_default_budget(user["income"])
    
    await db["budgets"].update_one(
        {"user_id": user_id},
        {"$set": {
            "allocations": [a.model_dump() for a in default_allocations],
            "total_income": user["income"],
            "updated_at": datetime.utcnow()
        }}
    )
    
    return {"message": "Budget reset to defaults", "allocations": [a.model_dump() for a in default_allocations]}
