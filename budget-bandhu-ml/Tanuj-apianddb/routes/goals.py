"""
Goals Routes - CRUD + LSTMForecaster ETA
BudgetBandhu API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime, timedelta
from bson import ObjectId

from api.database import get_database
from api.models.goal import Goal, GoalCreate, GoalResponse, GoalContribution, Milestone
from intelligence.forecaster import LSTMSavingsForecaster

router = APIRouter(prefix="/api/v1/goals", tags=["Goals"])

# Initialize LSTM Forecaster
try:
    forecaster = LSTMSavingsForecaster(model_path="models/lstm_forecaster/model.pth")
    FORECASTER_AVAILABLE = True
except Exception as e:
    print(f"[GOALS] LSTM not loaded: {e}")
    FORECASTER_AVAILABLE = False


@router.get("/{user_id}", response_model=List[dict])
async def get_goals(user_id: str, db=Depends(get_database)):
    """Get all goals for a user with ETA predictions"""
    goals = await db["goals"].find({"user_id": user_id}).to_list(20)
    
    # Enrich with progress and ETA
    enriched_goals = []
    for goal in goals:
        goal["id"] = str(goal.pop("_id"))
        goal["progress_percentage"] = min(100, (goal["current"] / goal["target"]) * 100) if goal["target"] > 0 else 0
        goal["remaining"] = max(0, goal["target"] - goal["current"])
        goal["on_track"] = goal["progress_percentage"] >= 40  # Simple heuristic
        
        # Calculate ETA using savings rate
        if goal["remaining"] > 0:
            # Get average monthly contribution
            monthly_contribution = await get_average_contribution(db, user_id, goal["id"])
            if monthly_contribution > 0:
                eta_months = goal["remaining"] / monthly_contribution
                goal["eta_days"] = int(eta_months * 30)
            else:
                goal["eta_days"] = None
        else:
            goal["eta_days"] = 0  # Already complete
        
        enriched_goals.append(goal)
    
    return enriched_goals


@router.post("", response_model=dict)
async def create_goal(goal_data: GoalCreate, db=Depends(get_database)):
    """Create a new financial goal"""
    
    # Generate milestones (25%, 50%, 75%)
    milestones = [
        {"amount": goal_data.target * 0.25, "reached": False, "date": None},
        {"amount": goal_data.target * 0.50, "reached": False, "date": None},
        {"amount": goal_data.target * 0.75, "reached": False, "date": None},
    ]
    
    goal_doc = {
        "user_id": goal_data.user_id,
        "name": goal_data.name,
        "icon": goal_data.icon,
        "target": goal_data.target,
        "current": 0.0,
        "deadline": goal_data.deadline,
        "priority": goal_data.priority,
        "color": goal_data.color,
        "milestones": milestones,
        "created_at": datetime.utcnow()
    }
    
    result = await db["goals"].insert_one(goal_doc)
    
    print(f"[GOALS] Created: {goal_data.name} (₹{goal_data.target:,.0f})")
    
    return {
        "message": "Goal created",
        "goal_id": str(result.inserted_id),
        "name": goal_data.name,
        "target": goal_data.target
    }


@router.put("/{goal_id}/contribute")
async def contribute_to_goal(goal_id: str, contribution: GoalContribution, db=Depends(get_database)):
    """Add money to a goal"""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid goal ID")
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    new_current = goal["current"] + contribution.amount
    new_progress = (new_current / goal["target"]) * 100
    
    # Check milestones
    milestones = goal.get("milestones", [])
    milestones_reached = []
    for m in milestones:
        if not m["reached"] and new_current >= m["amount"]:
            m["reached"] = True
            m["date"] = datetime.utcnow().isoformat()
            milestones_reached.append(m["amount"])
    
    # Update goal
    await db["goals"].update_one(
        {"_id": ObjectId(goal_id)},
        {"$set": {
            "current": min(new_current, goal["target"]),
            "milestones": milestones
        }}
    )
    
    # Record contribution for ETA calculation
    await db["goal_contributions"].insert_one({
        "goal_id": goal_id,
        "user_id": goal["user_id"],
        "amount": contribution.amount,
        "date": datetime.utcnow()
    })
    
    is_complete = new_current >= goal["target"]
    
    print(f"[GOALS] Contribution: ₹{contribution.amount:,.0f} → {goal['name']} ({new_progress:.0f}%)")
    
    return {
        "message": "Contribution added",
        "new_current": min(new_current, goal["target"]),
        "progress_percentage": min(100, new_progress),
        "milestones_reached": milestones_reached,
        "is_complete": is_complete,
        "xp_earned": 10 + (100 if is_complete else 0) + (25 * len(milestones_reached))
    }


@router.get("/{goal_id}/eta")
async def get_goal_eta(goal_id: str, db=Depends(get_database)):
    """Get ETA prediction for a goal using LSTM"""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid goal ID")
    
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    remaining = goal["target"] - goal["current"]
    if remaining <= 0:
        return {"eta_days": 0, "message": "Goal completed!", "on_track": True}
    
    # Get contribution history
    contributions = await db["goal_contributions"].find({
        "goal_id": goal_id
    }).sort("date", 1).to_list(100)
    
    if len(contributions) < 3:
        return {
            "eta_days": None,
            "message": "Need more contribution history for accurate prediction",
            "on_track": None
        }
    
    # Use LSTM if available
    if FORECASTER_AVAILABLE:
        try:
            amounts = [c["amount"] for c in contributions]
            forecast_result = forecaster.process({
                "historical_spending": amounts,
                "horizon": "90d"
            })
            predicted_monthly = sum(forecast_result["result"]["predicted_spending"][:30])
            eta_days = int((remaining / predicted_monthly) * 30) if predicted_monthly > 0 else None
        except:
            # Fallback to simple average
            avg_contribution = sum(c["amount"] for c in contributions) / len(contributions)
            eta_days = int((remaining / avg_contribution)) if avg_contribution > 0 else None
    else:
        avg_contribution = sum(c["amount"] for c in contributions) / len(contributions)
        eta_days = int((remaining / avg_contribution)) if avg_contribution > 0 else None
    
    # Check if on track
    deadline = datetime.strptime(goal["deadline"], "%Y-%m-%d")
    days_until_deadline = (deadline - datetime.utcnow()).days
    on_track = eta_days <= days_until_deadline if eta_days else None
    
    return {
        "eta_days": eta_days,
        "days_until_deadline": days_until_deadline,
        "on_track": on_track,
        "message": f"{'On track!' if on_track else 'Behind schedule - increase contributions'}" if on_track is not None else "Calculating..."
    }


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, db=Depends(get_database)):
    """Delete a goal"""
    result = await db["goals"].delete_one({"_id": ObjectId(goal_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Goal not found")
    
    # Also delete contribution history
    await db["goal_contributions"].delete_many({"goal_id": goal_id})
    
    return {"message": "Goal deleted"}


async def get_average_contribution(db, user_id: str, goal_id: str) -> float:
    """Calculate average monthly contribution to a goal"""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    contributions = await db["goal_contributions"].find({
        "goal_id": goal_id,
        "date": {"$gte": thirty_days_ago}
    }).to_list(100)
    
    if not contributions:
        return 0
    
    return sum(c["amount"] for c in contributions)
