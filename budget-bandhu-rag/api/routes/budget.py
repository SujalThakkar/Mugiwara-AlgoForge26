"""
Budget Routes - Budget Management & ML Recommendations
Handles budget CRUD and Q-Learning recommendations

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/budget", tags=["Budget"])


class BudgetAllocation(BaseModel):
    category: str
    allocated: float
    spent: float = 0


class BudgetUpdate(BaseModel):
    user_id: str
    total_income: float
    allocations: List[BudgetAllocation]


# Default budget categories (50/30/20 rule adapted for India)
DEFAULT_CATEGORIES = [
    {"category": "Food & Drink", "percentage": 15},
    {"category": "Rent", "percentage": 25},
    {"category": "Utilities", "percentage": 5},
    {"category": "Travel", "percentage": 10},
    {"category": "Shopping", "percentage": 10},
    {"category": "Entertainment", "percentage": 5},
    {"category": "Health & Fitness", "percentage": 5},
    {"category": "Savings", "percentage": 20},
    {"category": "Other", "percentage": 5},
]


@router.get("/{user_id}")
async def get_budget(user_id: str, db=Depends(get_database)):
    """Get user's budget allocations"""
    budget = await db["budgets"].find_one({"user_id": user_id})
    
    if not budget:
        # Create default budget based on income
        user = await db["users"].find_one({"_id": user_id})
        income = user.get("income", 50000) if user else 50000
        
        default_allocations = [
            {
                "category": cat["category"],
                "allocated": income * cat["percentage"] / 100,
                "spent": 0
            }
            for cat in DEFAULT_CATEGORIES
        ]
        
        budget = {
            "user_id": user_id,
            "total_income": income,
            "allocations": default_allocations,
            "savings_target": income * 0.2,
            "current_savings": 0,
            "created_at": datetime.utcnow()
        }
        
        await db["budgets"].insert_one(budget)
    
    budget["id"] = str(budget.pop("_id", user_id))
    return budget


@router.put("/{user_id}")
async def update_budget(user_id: str, budget_data: BudgetUpdate, db=Depends(get_database)):
    """Update user's budget allocations"""
    try:
        allocations = [a.dict() for a in budget_data.allocations]
        
        result = await db["budgets"].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "total_income": budget_data.total_income,
                    "allocations": allocations,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        total_allocated = sum(a.allocated for a in budget_data.allocations)
        
        return {
            "message": "Budget updated",
            "total_allocated": total_allocated
        }
        
    except Exception as e:
        logger.error(f"[Budget] Update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/recommend")
async def get_recommendations(user_id: str, db=Depends(get_database)):
    """
    Get ML-based budget recommendations.
    Uses spending patterns to suggest optimal allocations.
    """
    try:
        # Get current budget
        budget = await db["budgets"].find_one({"user_id": user_id})
        if not budget:
            budget = await get_budget(user_id, db)
        
        # Get spending data
        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "type": "debit"
        }).sort("created_at", -1).limit(200)
        transactions = await txn_cursor.to_list(length=200)
        
        # Calculate actual spending by category
        actual_spending = {}
        for txn in transactions:
            cat = txn.get("category", "Other")
            actual_spending[cat] = actual_spending.get(cat, 0) + txn.get("amount", 0)
        
        # Generate recommendations
        recommendations = []
        total_savings_potential = 0
        
        for alloc in budget.get("allocations", []):
            cat = alloc["category"]
            allocated = alloc["allocated"]
            spent = actual_spending.get(cat, 0)
            
            # Calculate recommendation
            if spent > allocated * 1.2:  # Overspending
                recommended = min(spent, allocated * 1.3)
                change = "increase"
                reason = f"Consistently overspending in {cat}"
            elif spent < allocated * 0.5:  # Underspending
                recommended = max(spent, allocated * 0.7)
                change = "decrease"
                reason = f"Consistently underspending in {cat}"
                total_savings_potential += allocated - recommended
            else:
                recommended = allocated
                change = "maintain"
                reason = "Allocation matches spending pattern"
            
            recommendations.append({
                "category": cat,
                "current_allocation": allocated,
                "actual_spent": spent,
                "recommended": round(recommended, 2),
                "multiplier": round(spent / allocated, 2) if allocated > 0 else 1,
                "change": change,
                "reason": reason
            })
        
        return {
            "user_id": user_id,
            "recommendations": recommendations,
            "total_savings_potential": round(total_savings_potential, 2),
            "method": "spending_pattern_analysis"
        }
        
    except Exception as e:
        logger.error(f"[Budget] Recommend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/feedback")
async def submit_feedback(
    user_id: str, 
    category: str, 
    feedback: str,  # 'accepted' or 'rejected'
    db=Depends(get_database)
):
    """Record user feedback on budget recommendations for Q-Learning"""
    try:
        await db["budget_feedback"].insert_one({
            "user_id": user_id,
            "category": category,
            "feedback": feedback,
            "timestamp": datetime.utcnow()
        })
        
        return {"message": f"Feedback recorded for {category}"}
        
    except Exception as e:
        logger.error(f"[Budget] Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/reset")
async def reset_budget(user_id: str, db=Depends(get_database)):
    """Reset budget to default allocations"""
    try:
        user = await db["users"].find_one({"_id": user_id})
        income = user.get("income", 50000) if user else 50000
        
        default_allocations = [
            {
                "category": cat["category"],
                "allocated": income * cat["percentage"] / 100,
                "spent": 0
            }
            for cat in DEFAULT_CATEGORIES
        ]
        
        await db["budgets"].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "allocations": default_allocations,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "message": "Budget reset to defaults",
            "allocations": default_allocations
        }
        
    except Exception as e:
        logger.error(f"[Budget] Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
