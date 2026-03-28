"""
Goals Routes - Savings Goals Management
CRUD operations for financial goals with ML-powered ETA tracking.

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
import logging

from api.database import get_database
from intelligence.ml_client import goal_eta as ml_goal_eta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/goals", tags=["Goals"])


class GoalCreate(BaseModel):
    model_config = {"populate_by_name": True}
    user_id: str
    name: str
    icon: str = "🎯"
    # Accept both "target" and "target_amount"
    target: Optional[float] = None
    target_amount: Optional[float] = None
    # Accept both "deadline" and "target_date"
    deadline: Optional[str] = None
    target_date: Optional[str] = None
    priority: str = "medium"  # low, medium, high
    color: str = "#10B981"
    current_amount: Optional[float] = 0  # for seeding current progress

    def resolved_target(self) -> float:
        return self.target or self.target_amount or 0

    def resolved_deadline(self) -> str:
        return self.deadline or self.target_date or ""


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


async def _enrich_goal_with_eta(goal_dict: dict, txn_list: list[dict]) -> dict:
    """Call ML service for a single goal's ETA. Graceful fallback on failure."""
    try:
        ml_result = await ml_goal_eta(
            goal={
                "name":           goal_dict.get("name", "Goal"),
                "target_amount":  goal_dict.get("target", 0),
                "current_amount": goal_dict.get("current", 0),
                "target_date":    str(goal_dict.get("deadline", "")),
                "category":       goal_dict.get("category", "Savings"),
                "priority":       goal_dict.get("priority", "medium"),
                "notes":          ""
            },
            transactions=txn_list,
        )
        goal_dict["eta_days"] = ml_result.get("eta_days")
        goal_dict["on_track"] = ml_result.get("on_track", False)
        goal_dict["projected_completion_date"] = ml_result.get("projected_completion_date")
        goal_dict["shortfall_risk"] = ml_result.get("shortfall_risk", False)
        goal_dict["ai_verified"] = True
    except Exception as e:
        logger.warning(f"[Goals] ML goal-eta failed for {goal_dict.get('name')}: {e}")
        # Keep the simple math fallback
        goal_dict["ai_verified"] = False
    return goal_dict


@router.get("/{user_id}")
async def get_goals(user_id: str, db=Depends(get_database)):
    """Get all goals for a user, enriched with ML-computed ETA."""
    try:
        cursor = db["goals"].find({"user_id": user_id}).sort("deadline", 1)
        goals = await cursor.to_list(length=50)

        # Fetch last 60 days of txns ONCE for all goals
        sixty_days_ago = datetime.utcnow() - timedelta(days=60)
        txn_cursor = db["transactions"].find({
            "user_id": user_id,
            "created_at": {"$gte": sixty_days_ago}
        })
        recent_txns = await txn_cursor.to_list(length=1000)
        serialized_txns = []
        for t in recent_txns:
            d = t.get("date") or t.get("created_at", datetime.utcnow())
            if isinstance(d, datetime):
                d = d.strftime("%Y-%m-%d")
            serialized_txns.append({
                "date": str(d)[:10],
                "amount": t.get("amount", 0),
                "type": t.get("type", "debit"),
                "category": t.get("category", "Other"),
            })

        result = []
        tasks = []
        for goal in goals:
            progress = (goal.get("current", 0) / goal.get("target", 1)) * 100
            remaining = goal.get("target", 0) - goal.get("current", 0)

            # Simple deadline-based ETA (fallback)
            try:
                deadline = datetime.fromisoformat(goal.get("deadline", datetime.utcnow().isoformat()[:10]))
            except (ValueError, TypeError):
                deadline = datetime.utcnow() + timedelta(days=365)
            days_until = (deadline - datetime.utcnow()).days

            goal_dict = {
                "id": str(goal["_id"]),
                "user_id": goal["user_id"],
                "name": goal["name"],
                "icon": goal.get("icon", "🎯"),
                "target": goal["target"],
                "current": goal.get("current", 0),
                "deadline": goal.get("deadline", ""),
                "priority": goal.get("priority", "medium"),
                "color": goal.get("color", "#10B981"),
                "progress_percentage": round(progress, 1),
                "remaining": remaining,
                "on_track": remaining <= 0 or (days_until > 0 and remaining / days_until < goal["target"] / 30),
                "eta_days": days_until if days_until > 0 else None,
                "projected_completion_date": None,
                "shortfall_risk": False,
                "ai_verified": False,
                "milestones": goal.get("milestones", [])
            }
            result.append(goal_dict)
            tasks.append(_enrich_goal_with_eta(goal_dict, serialized_txns))

        # Run all ML calls in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return result

    except Exception as e:
        logger.error(f"[Goals] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_goal(goal: GoalCreate, db=Depends(get_database)):
    """Create a new savings goal"""
    try:
        t = goal.resolved_target()
        d = goal.resolved_deadline()
        if t <= 0:
            raise HTTPException(status_code=422, detail="target / target_amount must be > 0")
        goal_doc = {
            "user_id": goal.user_id,
            "name": goal.name,
            "icon": goal.icon,
            "target": t,
            "current": goal.current_amount or 0,
            "deadline": d,
            "priority": goal.priority,
            "color": goal.color,
            "milestones": calculate_milestones(t),
            "created_at": datetime.utcnow()
        }

        result = await db["goals"].insert_one(goal_doc)

        return {
            "goal_id": str(result.inserted_id),
            "name": goal.name,
            "target": t
        }

    except HTTPException:
        raise
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
    """Get estimated time to reach goal (standalone endpoint)"""
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
