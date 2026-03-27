"""
Goals Routes - Savings Goals Management
CRUD operations for financial goals with progress tracking

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/goals", tags=["Goals"])


class GoalCreate(BaseModel):
    user_id: str
    name: str
    icon: str = "🎯"
    target: float
    deadline: str  # ISO date string
    priority: str = "medium"  # low, medium, high
    color: str = "#10B981"


class GoalContribute(BaseModel):
    amount: float


def calculate_milestones(target: float) -> List[dict]:
    """Generate milestone checkpoints at 25%, 50%, 75%"""
    return [
        {"amount": target * 0.25, "reached": False, "date": None},
        {"amount": target * 0.50, "reached": False, "date": None},
        {"amount": target * 0.75, "reached": False, "date": None},
        {"amount": target, "reached": False, "date": None},
    ]


@router.get("/{user_id}")
async def get_goals(user_id: str, db=Depends(get_database)):
    """Get all goals for a user"""
    try:
        cursor = db["goals"].find({"user_id": user_id}).sort("deadline", 1)
        goals = await cursor.to_list(length=50)
        
        result = []
        for goal in goals:
            progress = (goal.get("current", 0) / goal.get("target", 1)) * 100
            remaining = goal.get("target", 0) - goal.get("current", 0)
            
            # Calculate ETA
            deadline = datetime.fromisoformat(goal.get("deadline", datetime.utcnow().isoformat()[:10]))
            days_until = (deadline - datetime.utcnow()).days
            
            result.append({
                "id": str(goal["_id"]),
                "user_id": goal["user_id"],
                "name": goal["name"],
                "icon": goal.get("icon", "🎯"),
                "target": goal["target"],
                "current": goal.get("current", 0),
                "deadline": goal["deadline"],
                "priority": goal.get("priority", "medium"),
                "color": goal.get("color", "#10B981"),
                "progress_percentage": round(progress, 1),
                "remaining": remaining,
                "on_track": remaining <= 0 or (days_until > 0 and remaining / days_until < goal["target"] / 30),
                "eta_days": days_until if days_until > 0 else None,
                "milestones": goal.get("milestones", [])
            })
        
        return result
        
    except Exception as e:
        logger.error(f"[Goals] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_goal(goal: GoalCreate, db=Depends(get_database)):
    """Create a new savings goal"""
    try:
        goal_doc = {
            "user_id": goal.user_id,
            "name": goal.name,
            "icon": goal.icon,
            "target": goal.target,
            "current": 0,
            "deadline": goal.deadline,
            "priority": goal.priority,
            "color": goal.color,
            "milestones": calculate_milestones(goal.target),
            "created_at": datetime.utcnow()
        }
        
        result = await db["goals"].insert_one(goal_doc)
        
        return {
            "goal_id": str(result.inserted_id),
            "name": goal.name,
            "target": goal.target
        }
        
    except Exception as e:
        logger.error(f"[Goals] Create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{goal_id}/contribute")
async def contribute_to_goal(goal_id: str, contribution: GoalContribute, db=Depends(get_database)):
    """Add funds to a goal"""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        new_current = goal.get("current", 0) + contribution.amount
        progress = (new_current / goal["target"]) * 100
        
        # Check milestones
        milestones = goal.get("milestones", [])
        milestones_reached = []
        for i, milestone in enumerate(milestones):
            if not milestone["reached"] and new_current >= milestone["amount"]:
                milestones[i]["reached"] = True
                milestones[i]["date"] = datetime.utcnow().isoformat()
                milestones_reached.append(i + 1)
        
        # Update goal
        await db["goals"].update_one(
            {"_id": ObjectId(goal_id)},
            {
                "$set": {
                    "current": new_current,
                    "milestones": milestones,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        is_complete = new_current >= goal["target"]
        xp_earned = 10 + (25 * len(milestones_reached)) + (100 if is_complete else 0)
        
        return {
            "new_current": new_current,
            "progress_percentage": round(progress, 1),
            "milestones_reached": milestones_reached,
            "is_complete": is_complete,
            "xp_earned": xp_earned
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Contribute error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{goal_id}/eta")
async def get_goal_eta(goal_id: str, db=Depends(get_database)):
    """Get estimated time to reach goal"""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        deadline = datetime.fromisoformat(goal.get("deadline", datetime.utcnow().isoformat()[:10]))
        days_until = (deadline - datetime.utcnow()).days
        remaining = goal["target"] - goal.get("current", 0)
        
        if remaining <= 0:
            return {
                "eta_days": 0,
                "days_until_deadline": days_until,
                "on_track": True,
                "message": "Goal completed! 🎉"
            }
        
        # Estimate based on average savings rate
        avg_daily = goal.get("current", 0) / max(1, (datetime.utcnow() - goal.get("created_at", datetime.utcnow())).days)
        eta_days = int(remaining / avg_daily) if avg_daily > 0 else None
        
        return {
            "eta_days": eta_days,
            "days_until_deadline": days_until,
            "on_track": eta_days is not None and eta_days <= days_until,
            "message": "On track!" if eta_days and eta_days <= days_until else "Need to increase savings"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] ETA error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, db=Depends(get_database)):
    """Delete a goal"""
    try:
        result = await db["goals"].delete_one({"_id": ObjectId(goal_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Goal not found")
        
        return {"message": "Goal deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
