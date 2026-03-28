"""
Budget Routes - Budget Management & ML Recommendations
Handles budget CRUD and Q-Learning recommendations with MongoDB-persisted PolicyLearner state.

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging
import math

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


class FeedbackBody(BaseModel):
    accepted: bool
    category: str
    user_id: str


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

# ── PolicyLearner helpers (Q-Learning persistence via MongoDB) ────────────

LEARNING_RATE = 0.08
DISCOUNT_FACTOR = 0.95
DEFAULT_MULTIPLIER = 1.0


async def _load_policy_state(db, user_id: str) -> dict:
    """Load PolicyLearner state from MongoDB, or return defaults."""
    state = await db["policy_state"].find_one({"user_id": user_id})
    if state:
        return state
    return {
        "user_id": user_id,
        "budget_multipliers": {},
        "success_count": {},
        "failure_count": {},
        "episode_count": 0,
        "last_updated": datetime.utcnow(),
    }


async def _save_policy_state(db, user_id: str, state: dict):
    """Upsert PolicyLearner state to MongoDB."""
    state["last_updated"] = datetime.utcnow()
    await db["policy_state"].update_one(
        {"user_id": user_id},
        {"$set": state},
        upsert=True,
    )


def _q_recommend(category: str, current_spend: float, allocated: float, state: dict) -> dict:
    """Run one Q-Learning step for a category and return a recommendation."""
    multiplier = state.get("budget_multipliers", {}).get(category, DEFAULT_MULTIPLIER)
    successes = state.get("success_count", {}).get(category, 0)
    failures = state.get("failure_count", {}).get(category, 0)

    # Confidence rises with more episodes
    total_feedback = successes + failures
    confidence = min(0.95, 0.50 + 0.03 * total_feedback)

    # Suggested budget = allocated * multiplier (clamped 0.5x – 1.5x)
    suggested = round(allocated * multiplier, 2)
    savings_potential = max(0, round(current_spend - suggested, 2))

    if current_spend > allocated * 1.15:
        reasoning = f"Your {category} spending (₹{current_spend:,.0f}) exceeds budget by {((current_spend / allocated - 1) * 100):.0f}%. Consider trimming."
    elif current_spend < allocated * 0.5:
        reasoning = f"You're well under budget in {category}. Consider reallocating ₹{round(allocated - current_spend):,.0f} to savings."
    else:
        reasoning = f"{category} spending is within healthy range."

    return {
        "category": category,
        "current_spend": round(current_spend, 2),
        "suggested_budget": suggested,
        "savings_potential": savings_potential,
        "reasoning": reasoning,
        "confidence": round(confidence, 2),
    }


# ── Routes ────────────────────────────────────────────────────────────────

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
    Uses real spending data + PolicyLearner Q-Learning state persisted in MongoDB.
    """
    try:
        # 1. Load budget
        budget = await db["budgets"].find_one({"user_id": user_id})
        if not budget:
            budget = await get_budget(user_id, db)

        # 2. Fetch REAL last-30-day spending per category from MongoDB
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        thirty_days_ago_str = thirty_days_ago.strftime("%Y-%m-%d")

        # Query both created_at (datetime) and date (ISO string) — whichever is present
        pipeline_created_at = [
            {"$match": {
                "user_id": user_id,
                "type": {"$in": ["Debit", "debit"]},
                "created_at": {"$gte": thirty_days_ago}
            }},
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"}
            }}
        ]
        pipeline_date_str = [
            {"$match": {
                "user_id": user_id,
                "type": {"$in": ["Debit", "debit"]},
                "date": {"$gte": thirty_days_ago_str}
            }},
            {"$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"}
            }}
        ]
        spending_raw_1 = await db["transactions"].aggregate(pipeline_created_at).to_list(length=100)
        spending_raw_2 = await db["transactions"].aggregate(pipeline_date_str).to_list(length=100)
        # Merge: use max per category to avoid double-counting transactions
        # that appear in both result sets (same docs can match both queries)
        real_spending: dict = {}
        for s in spending_raw_1:
            cat = s["_id"] or "Other"
            real_spending[cat] = max(real_spending.get(cat, 0), s["total"])
        for s in spending_raw_2:
            cat = s["_id"] or "Other"
            real_spending[cat] = max(real_spending.get(cat, 0), s["total"])

        # 3. Load PolicyLearner state from MongoDB
        policy_state = await _load_policy_state(db, user_id)
        
        episode_count = policy_state.get("episode_count", 0)

        # 4. Generate recommendations per category using REAL spending
        recommendations = []
        for category, actual_spend in real_spending.items():
            if actual_spend > 0:
                multiplier = policy_state.get("budget_multipliers", {}).get(category, 1.0)
                suggested  = actual_spend * multiplier * 0.9
                recommendations.append({
                    "category":          category,
                    "current_spend":     actual_spend,    
                    "suggested_budget":  round(suggested, 0),
                    "savings_potential": round(max(0, actual_spend - suggested), 0),
                    "reasoning":         f"Based on your spending pattern in {category}.",
                    "confidence":        min(0.5 + (episode_count * 0.01), 0.95)
                })

        return {
            "user_id": user_id,
            "recommendations": recommendations,
            "total_savings_potential": sum(r["savings_potential"] for r in recommendations),
            "model_version": "PolicyLearner-v1",
            "episodes_trained": episode_count,
        }

    except Exception as e:
        logger.error(f"[Budget] Recommend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{budget_id}/feedback")
async def submit_feedback(budget_id: str, body: dict, db=Depends(get_database)):
    """
    Record user feedback on budget recommendations for Q-Learning.
    Updates the PolicyLearner multiplier and persists to MongoDB.
    """
    try:
        user_id = body.get("user_id")
        category = body.get("category")
        accepted = body.get("accepted", False)

        # 1. Load state
        state = await _load_policy_state(db, user_id)
        multipliers = state.get("budget_multipliers", {})
        successes = state.get("success_count", {})
        failures = state.get("failure_count", {})

        current_mult = multipliers.get(category, DEFAULT_MULTIPLIER)

        # 2. Q-Learning update
        if accepted:
            # Reinforce: move multiplier toward current value (tighter)
            reward = 1.0
            successes[category] = successes.get(category, 0) + 1
        else:
            # Penalise: relax multiplier back toward 1.0
            reward = -0.5
            failures[category] = failures.get(category, 0) + 1

        new_mult = current_mult + LEARNING_RATE * (reward + DISCOUNT_FACTOR * DEFAULT_MULTIPLIER - current_mult)
        new_mult = max(0.5, min(1.5, new_mult))  # clamp

        multipliers[category] = round(new_mult, 4)
        state["budget_multipliers"] = multipliers
        state["success_count"] = successes
        state["failure_count"] = failures
        state["episode_count"] = state.get("episode_count", 0) + 1

        # 3. Save to MongoDB
        await _save_policy_state(db, user_id, state)

        # 4. Also log raw feedback
        await db["budget_feedback"].insert_one({
            "user_id": user_id,
            "category": category,
            "feedback": "accepted" if accepted else "rejected",
            "timestamp": datetime.utcnow()
        })

        return {
            "status": "ok",
            "new_multiplier": round(new_mult, 4),
            "message": f"Thanks! {category} policy updated (episode #{state['episode_count']})."
        }

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
