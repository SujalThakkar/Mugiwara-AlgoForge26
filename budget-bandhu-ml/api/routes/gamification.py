"""
Gamification Routes - XP, Levels, Badges, Leaderboard
Engagement features for user motivation

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from typing import List, Dict
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/gamification", tags=["Gamification"])


# Level thresholds
LEVEL_THRESHOLDS = [
    100, 250, 500, 800, 1200, 1700, 2300, 3000, 3800, 4700,  # 1-10
    5700, 6800, 8000, 9300, 10700, 12200, 13800, 15500, 17300, 19200  # 11-20
]

LEVEL_TITLES = [
    "Novice Saver", "Budget Beginner", "Cash Conscious", "Money Mindful",
    "Savings Starter", "Budget Builder", "Financial Finder", "Money Manager",
    "Wealth Watcher", "Investment Initiate", "Portfolio Pioneer", "Asset Achiever",
    "Wealth Warrior", "Finance Fanatic", "Money Master", "Budget Boss",
    "Savings Sage", "Investment Idol", "Wealth Wizard", "Financial Freedom Finder"
]

# Badge definitions
BADGES = [
    {"id": "first_transaction", "name": "First Steps", "description": "Add your first transaction", "icon": "🎯", "trigger": "transaction_count >= 1"},
    {"id": "ten_transactions", "name": "Getting Started", "description": "Log 10 transactions", "icon": "📊", "trigger": "transaction_count >= 10"},
    {"id": "hundred_transactions", "name": "Dedicated Tracker", "description": "Log 100 transactions", "icon": "💯", "trigger": "transaction_count >= 100"},
    {"id": "first_goal", "name": "Goal Setter", "description": "Create your first savings goal", "icon": "🎯", "trigger": "goal_count >= 1"},
    {"id": "goal_complete", "name": "Goal Crusher", "description": "Complete a savings goal", "icon": "🏆", "trigger": "goals_completed >= 1"},
    {"id": "budget_master", "name": "Budget Master", "description": "Stay under budget for a month", "icon": "💰", "trigger": "under_budget_months >= 1"},
    {"id": "streak_7", "name": "Week Warrior", "description": "7-day login streak", "icon": "🔥", "trigger": "streak_days >= 7"},
    {"id": "streak_30", "name": "Monthly Champion", "description": "30-day login streak", "icon": "⭐", "trigger": "streak_days >= 30"},
    {"id": "saver_10k", "name": "10K Club", "description": "Save ₹10,000 total", "icon": "💵", "trigger": "total_saved >= 10000"},
    {"id": "saver_100k", "name": "Lakh Saver", "description": "Save ₹1,00,000 total", "icon": "💎", "trigger": "total_saved >= 100000"},
]


def calculate_level(total_xp: int) -> Dict:
    """Calculate level from total XP"""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_xp >= threshold:
            level = i + 2
        else:
            break
    
    if level > len(LEVEL_THRESHOLDS):
        level = len(LEVEL_THRESHOLDS) + 1
    
    current_threshold = LEVEL_THRESHOLDS[level - 2] if level > 1 else 0
    next_threshold = LEVEL_THRESHOLDS[level - 1] if level <= len(LEVEL_THRESHOLDS) else LEVEL_THRESHOLDS[-1] + 1000
    
    return {
        "level": level,
        "current_xp": total_xp - current_threshold,
        "xp_to_next_level": next_threshold - total_xp,
        "title": LEVEL_TITLES[min(level - 1, len(LEVEL_TITLES) - 1)]
    }


async def get_or_create_gamification(user_id: str, db):
    """Get or initialize gamification data for a user"""
    gam = await db["gamification"].find_one({"user_id": user_id})
    
    if not gam:
        gam = {
            "user_id": user_id,
            "total_xp": 0,
            "badges": [{"id": b["id"], "unlocked": False, "unlocked_at": None} for b in BADGES],
            "challenges_completed": 0,
            "streak_days": 0,
            "last_login": None,
            "created_at": datetime.utcnow()
        }
        await db["gamification"].insert_one(gam)
    
    return gam


@router.get("/{user_id}")
async def get_gamification(user_id: str, db=Depends(get_database)):
    """Get gamification data for a user"""
    try:
        gam = await get_or_create_gamification(user_id, db)
        level_info = calculate_level(gam.get("total_xp", 0))
        
        # Merge badge definitions with user's unlock status
        user_badges = {b["id"]: b for b in gam.get("badges", [])}
        badges = []
        for badge_def in BADGES:
            user_badge = user_badges.get(badge_def["id"], {})
            badges.append({
                **badge_def,
                "unlocked": user_badge.get("unlocked", False),
                "unlocked_at": user_badge.get("unlocked_at"),
                "trigger_description": badge_def["trigger"]
            })
        
        return {
            "id": str(gam.get("_id", user_id)),
            "user_id": user_id,
            "level_info": level_info,
            "total_xp": gam.get("total_xp", 0),
            "badges": badges,
            "challenges_completed": gam.get("challenges_completed", 0),
            "streak_days": gam.get("streak_days", 0)
        }
        
    except Exception as e:
        logger.error(f"[Gamification] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/xp")
async def add_xp(user_id: str, amount: int, reason: str, db=Depends(get_database)):
    """Add XP to a user"""
    try:
        gam = await get_or_create_gamification(user_id, db)
        old_level = calculate_level(gam.get("total_xp", 0))["level"]
        
        new_total = gam.get("total_xp", 0) + amount
        new_level_info = calculate_level(new_total)
        
        await db["gamification"].update_one(
            {"user_id": user_id},
            {
                "$set": {"total_xp": new_total, "updated_at": datetime.utcnow()},
                "$push": {"xp_history": {"amount": amount, "reason": reason, "timestamp": datetime.utcnow()}}
            }
        )
        
        leveled_up = new_level_info["level"] > old_level
        
        return {
            "new_total_xp": new_total,
            "level_info": new_level_info,
            "leveled_up": leveled_up,
            "new_level": new_level_info["level"] if leveled_up else None
        }
        
    except Exception as e:
        logger.error(f"[Gamification] Add XP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/check-badges")
async def check_badges(user_id: str, db=Depends(get_database)):
    """Check and unlock any earned badges"""
    try:
        gam = await get_or_create_gamification(user_id, db)
        
        # Gather stats
        txn_count = await db["transactions"].count_documents({"user_id": user_id})
        goal_count = await db["goals"].count_documents({"user_id": user_id})
        
        # Check completed goals
        goals = await db["goals"].find({"user_id": user_id}).to_list(length=100)
        goals_completed = sum(1 for g in goals if g.get("current", 0) >= g.get("target", 1))
        total_saved = sum(g.get("current", 0) for g in goals)
        
        stats = {
            "transaction_count": txn_count,
            "goal_count": goal_count,
            "goals_completed": goals_completed,
            "total_saved": total_saved,
            "streak_days": gam.get("streak_days", 0),
            "under_budget_months": 0  # TODO: Calculate from budget history
        }
        
        # Check each badge
        newly_unlocked = []
        badges = gam.get("badges", [])
        
        for i, badge in enumerate(badges):
            if badge.get("unlocked"):
                continue
            
            badge_def = next((b for b in BADGES if b["id"] == badge["id"]), None)
            if not badge_def:
                continue
            
            # Evaluate trigger
            try:
                trigger = badge_def["trigger"]
                if eval(trigger, {"__builtins__": {}}, stats):
                    badges[i]["unlocked"] = True
                    badges[i]["unlocked_at"] = datetime.utcnow().isoformat()
                    newly_unlocked.append({
                        "id": badge_def["id"],
                        "name": badge_def["name"],
                        "icon": badge_def["icon"]
                    })
            except:
                pass
        
        # Update if any unlocked
        xp_earned = 0
        if newly_unlocked:
            xp_earned = 50 * len(newly_unlocked)
            await db["gamification"].update_one(
                {"user_id": user_id},
                {
                    "$set": {"badges": badges},
                    "$inc": {"total_xp": xp_earned}
                }
            )
        
        return {
            "checked": len(BADGES),
            "newly_unlocked": newly_unlocked,
            "xp_earned": xp_earned
        }
        
    except Exception as e:
        logger.error(f"[Gamification] Check badges error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard/{user_id}")
async def get_leaderboard(user_id: str, limit: int = 10, db=Depends(get_database)):
    """Get XP leaderboard"""
    try:
        cursor = db["gamification"].find().sort("total_xp", -1).limit(limit)
        entries = await cursor.to_list(length=limit)
        
        leaderboard = []
        user_rank = None
        
        for i, entry in enumerate(entries):
            level_info = calculate_level(entry.get("total_xp", 0))
            
            # Get user name
            user = await db["users"].find_one({"_id": entry["user_id"]})
            name = user.get("name", "Anonymous") if user else "Anonymous"
            
            is_current = entry["user_id"] == user_id
            
            leaderboard.append({
                "rank": i + 1,
                "user_id": entry["user_id"],
                "name": name,
                "total_xp": entry.get("total_xp", 0),
                "level": level_info["level"],
                "is_current_user": is_current
            })
            
            if is_current:
                user_rank = {
                    "rank": i + 1,
                    "total_xp": entry.get("total_xp", 0),
                    "level": level_info["level"]
                }
        
        return {
            "leaderboard": leaderboard,
            "user_rank": user_rank
        }
        
    except Exception as e:
        logger.error(f"[Gamification] Leaderboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
