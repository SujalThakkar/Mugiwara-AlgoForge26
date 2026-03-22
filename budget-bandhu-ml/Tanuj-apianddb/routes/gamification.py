"""
Gamification Routes - XP, Badges, Leaderboard with ML Triggers
BudgetBandhu API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime
from bson import ObjectId

from api.database import get_database
from api.models.gamification import Gamification, LevelInfo, ML_BADGES, XP_REWARDS

router = APIRouter(prefix="/api/v1/gamification", tags=["Gamification"])


# Level thresholds
LEVEL_THRESHOLDS = [
    (1, 0, "Finance Beginner"),
    (2, 100, "Money Tracker"),
    (3, 250, "Budget Planner"),
    (4, 500, "Savings Pro"),
    (5, 1000, "Financial Wizard"),
    (6, 2000, "Money Master"),
    (7, 4000, "Wealth Builder"),
    (8, 7500, "Investment Guru"),
    (9, 12500, "Financial Expert"),
    (10, 20000, "Money Legend"),
]


def calculate_level(total_xp: int) -> LevelInfo:
    """Calculate level info from total XP"""
    current_level = 1
    title = "Finance Beginner"
    
    for level, threshold, level_title in LEVEL_THRESHOLDS:
        if total_xp >= threshold:
            current_level = level
            title = level_title
    
    # Find XP needed for next level
    next_level_idx = current_level if current_level < len(LEVEL_THRESHOLDS) else len(LEVEL_THRESHOLDS) - 1
    current_threshold = LEVEL_THRESHOLDS[current_level - 1][1]
    next_threshold = LEVEL_THRESHOLDS[next_level_idx][1]
    
    xp_in_level = total_xp - current_threshold
    xp_to_next = next_threshold - current_threshold
    
    return LevelInfo(
        level=current_level,
        current_xp=xp_in_level,
        xp_to_next_level=xp_to_next,
        title=title
    )


@router.get("/{user_id}")
async def get_gamification(user_id: str, db=Depends(get_database)):
    """Get user's gamification profile (XP, level, badges)"""
    gamification = await db["gamification"].find_one({"user_id": user_id})
    
    if not gamification:
        raise HTTPException(status_code=404, detail="Gamification profile not found")
    
    gamification["id"] = str(gamification.pop("_id"))
    
    # Recalculate level from total XP
    gamification["level_info"] = calculate_level(gamification["total_xp"]).model_dump()
    
    return gamification


@router.post("/{user_id}/xp")
async def add_xp(user_id: str, amount: int, reason: str, db=Depends(get_database)):
    """Add XP to user (called after actions)"""
    if amount <= 0:
        raise HTTPException(status_code=400, detail="XP amount must be positive")
    
    # Get current gamification
    gamification = await db["gamification"].find_one({"user_id": user_id})
    if not gamification:
        raise HTTPException(status_code=404, detail="Gamification profile not found")
    
    old_total = gamification["total_xp"]
    new_total = old_total + amount
    
    # Calculate new level
    old_level_info = calculate_level(old_total)
    new_level_info = calculate_level(new_total)
    
    leveled_up = new_level_info.level > old_level_info.level
    
    # Update
    await db["gamification"].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "total_xp": new_total,
                "level_info": new_level_info.model_dump(),
                "last_active": datetime.utcnow()
            }
        }
    )
    
    print(f"[GAMIFICATION] +{amount} XP for {user_id} ({reason})")
    
    return {
        "message": f"+{amount} XP!",
        "reason": reason,
        "new_total_xp": new_total,
        "level_info": new_level_info.model_dump(),
        "leveled_up": leveled_up,
        "new_level": new_level_info.level if leveled_up else None
    }


@router.post("/{user_id}/check-badges")
async def check_ml_badges(user_id: str, db=Depends(get_database)):
    """
    Check and unlock ML-triggered badges.
    Called after significant actions (transaction upload, insights view, etc.)
    """
    gamification = await db["gamification"].find_one({"user_id": user_id})
    if not gamification:
        raise HTTPException(status_code=404, detail="Gamification profile not found")
    
    badges = gamification.get("badges", [])
    newly_unlocked = []
    total_xp_earned = 0
    
    # Get stats for badge checks
    stats = await get_user_stats_for_badges(db, user_id)
    
    for badge in badges:
        if badge["unlocked"]:
            continue
        
        # Check badge condition
        unlocked = check_badge_condition(badge["id"], stats)
        
        if unlocked:
            badge["unlocked"] = True
            badge["unlocked_at"] = datetime.utcnow().isoformat()
            newly_unlocked.append(badge)
            
            # Find XP reward
            badge_def = next((b for b in ML_BADGES if b["id"] == badge["id"]), None)
            if badge_def:
                total_xp_earned += badge_def["xp_reward"]
    
    # Update badges
    if newly_unlocked:
        await db["gamification"].update_one(
            {"user_id": user_id},
            {"$set": {"badges": badges}}
        )
        
        # Add XP for unlocked badges
        if total_xp_earned > 0:
            await add_xp(user_id, total_xp_earned, f"Unlocked {len(newly_unlocked)} badge(s)", db)
    
    return {
        "checked": len(badges),
        "newly_unlocked": [{"id": b["id"], "name": b["name"], "icon": b["icon"]} for b in newly_unlocked],
        "xp_earned": total_xp_earned
    }


def check_badge_condition(badge_id: str, stats: dict) -> bool:
    """Check if badge condition is met"""
    conditions = {
        "transaction_master": stats["transactions_count"] >= 50,
        "anomaly_hunter": stats["anomalies_count"] >= 1,
        "savings_champion": stats["savings_rate"] > 0.20,
        "financial_ninja": stats["financial_score"] > 850,
        "budget_master": stats["all_under_budget"]
    }
    return conditions.get(badge_id, False)


async def get_user_stats_for_badges(db, user_id: str) -> dict:
    """Get all stats needed for badge checks"""
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)
    
    # Transaction count
    transactions_count = await db["transactions"].count_documents({"user_id": user_id})
    
    # Anomaly count
    anomalies_count = await db["transactions"].count_documents({
        "user_id": user_id,
        "is_anomaly": True
    })
    
    # Get spending and income for savings rate
    spending_pipeline = [
        {"$match": {"user_id": user_id, "type": "debit", "created_at": {"$gte": start_of_month}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    spending_result = await db["transactions"].aggregate(spending_pipeline).to_list(1)
    total_spent = spending_result[0]["total"] if spending_result else 0
    
    income_pipeline = [
        {"$match": {"user_id": user_id, "type": "credit", "created_at": {"$gte": start_of_month}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    income_result = await db["transactions"].aggregate(income_pipeline).to_list(1)
    total_income = income_result[0]["total"] if income_result else 0
    
    savings_rate = (total_income - total_spent) / total_income if total_income > 0 else 0
    
    # Financial score
    anomaly_rate = anomalies_count / transactions_count if transactions_count > 0 else 0
    financial_score = 800 - (total_spent / 10000 * 100) - (anomaly_rate * 200)
    financial_score = max(300, min(900, financial_score))
    
    # Check budget
    budget = await db["budgets"].find_one({"user_id": user_id})
    all_under_budget = True
    if budget:
        for alloc in budget.get("allocations", []):
            if alloc.get("spent", 0) > alloc.get("allocated", 0):
                all_under_budget = False
                break
    
    return {
        "transactions_count": transactions_count,
        "anomalies_count": anomalies_count,
        "savings_rate": savings_rate,
        "financial_score": financial_score,
        "all_under_budget": all_under_budget
    }


@router.get("/leaderboard/{user_id}")
async def get_leaderboard(user_id: str, limit: int = 10, db=Depends(get_database)):
    """Get leaderboard (top users by XP)"""
    # Get top users
    cursor = db["gamification"].find().sort("total_xp", -1).limit(limit)
    top_users = await cursor.to_list(limit)
    
    leaderboard = []
    for i, entry in enumerate(top_users):
        user = await db["users"].find_one({"_id": ObjectId(entry["user_id"])})
        leaderboard.append({
            "rank": i + 1,
            "user_id": entry["user_id"],
            "name": user["name"] if user else "Unknown",
            "total_xp": entry["total_xp"],
            "level": calculate_level(entry["total_xp"]).level,
            "is_current_user": entry["user_id"] == user_id
        })
    
    # Find current user's rank if not in top
    current_user_in_top = any(e["is_current_user"] for e in leaderboard)
    user_rank = None
    
    if not current_user_in_top:
        user_gamification = await db["gamification"].find_one({"user_id": user_id})
        if user_gamification:
            rank = await db["gamification"].count_documents({
                "total_xp": {"$gt": user_gamification["total_xp"]}
            }) + 1
            user_rank = {
                "rank": rank,
                "total_xp": user_gamification["total_xp"],
                "level": calculate_level(user_gamification["total_xp"]).level
            }
    
    return {
        "leaderboard": leaderboard,
        "user_rank": user_rank
    }
