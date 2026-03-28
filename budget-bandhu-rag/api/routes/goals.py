"""
Goals Routes — Goals 2.0
CRUD operations for financial goals with ML-powered ETA tracking + Web3 minting.
Supports: personal_csv, personal_crypto, group_csv, group_escrow.

Author: Aryan Lomte
Version: 2.0.0 (Goals 2.0 — ML ETA + Web3 minting)
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
import logging
import io
import csv

from api.database import get_database

# ML ETA client (upstream)
try:
    from intelligence.ml_client import goal_eta as ml_goal_eta
except ImportError:
    ml_goal_eta = None

# Web3 services (Goals 2.0)
try:
    from api.services.ipfs_service import generate_and_upload_badge
    from api.services.minting_service import mint_single_badge
except ImportError:
    generate_and_upload_badge = None
    mint_single_badge = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/goals", tags=["Goals"])

# ── Goal types ────────────────────────────────────────────────────────────────
GOAL_TYPES = ("personal_csv", "personal_crypto", "group_csv", "group_escrow")


# ── Schemas ───────────────────────────────────────────────────────────────────
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
    priority: str = "medium"             # low | medium | high
    color: str = "#10B981"
    goal_type: str = "personal_csv"      # see GOAL_TYPES
    wallet_address: Optional[str] = None # required for badge minting
    salary: Optional[float] = None       # for long-term mode
    current_amount: Optional[float] = 0  # for seeding current progress

    def resolved_target(self) -> float:
        return self.target or self.target_amount or 0

    def resolved_deadline(self) -> str:
        return self.deadline or self.target_date or ""


class GoalContribute(BaseModel):
    amount: float


class CompleteGoalRequest(BaseModel):
    wallet_address: str   # recipient of SBT
    mode: str = "manual"  # "manual" | "auto" (auto reads current from DB)


class ManualProgressUpdate(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to set or add")
    mode: str = Field(default="set", description="'set' = absolute, 'add' = incremental")


def calculate_milestones(target: float) -> List[dict]:
    return [
        {"amount": target * 0.25, "reached": False, "date": None},
        {"amount": target * 0.50, "reached": False, "date": None},
        {"amount": target * 0.75, "reached": False, "date": None},
        {"amount": target,        "reached": False, "date": None},
    ]


def _ipfs_to_image_url(token_uri: Optional[str]) -> Optional[str]:
    """Convert an IPFS token_uri to a Pinata gateway HTTP URL."""
    if not token_uri:
        return None
    cid = token_uri.replace("ipfs://", "")
    return f"https://gateway.pinata.cloud/ipfs/{cid}"


def _parse_csv_total_spend(content: bytes) -> float:
    """Parse a CSV and return total spend (debit amounts)."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="ignore")))
    total_spend = 0.0
    for row in reader:
        amount_val = (
            row.get("amount") or row.get("Amount") or
            row.get("debit") or row.get("Debit") or "0"
        )
        try:
            amount_val = float(str(amount_val).replace(",", "").replace("₹", ""))
            if amount_val > 0:
                total_spend += amount_val
        except ValueError:
            continue
    return round(total_spend, 2)


def _parse_csv_savings(content: bytes, salary: Optional[float] = None) -> dict:
    """
    Parse uploaded CSV and calculate savings.
    - Salary mode (salary provided):  savings = salary - total_spend
    - Forecast mode (no salary):      savings = 0.0 (caller must compute vs forecast)
    """
    total_spend = _parse_csv_total_spend(content)
    if salary:
        savings = max(0.0, salary - total_spend)
        mode = "salary"
    else:
        savings = 0.0
        mode = "forecast"
    return {"total_spend": total_spend, "savings": round(savings, 2), "mode": mode}


# ── ML ETA Enrichment (upstream) ─────────────────────────────────────────────
async def _enrich_goal_with_eta(goal_dict: dict, txn_list: list) -> dict:
    """Call ML service for a single goal's ETA. Graceful fallback on failure."""
    if ml_goal_eta is None:
        goal_dict["ai_verified"] = False
        return goal_dict
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
        goal_dict["ai_verified"] = False
    return goal_dict


# ── GET /api/v1/goals/{user_id} ──────────────────────────────────────────────
@router.get("/{user_id}")
async def get_goals(user_id: str, db=Depends(get_database)):
    """Get all goals for a user, enriched with ML-computed ETA + chain status."""
    try:
        cursor = db["goals"].find({"user_id": user_id}).sort("deadline", 1)
        goals  = await cursor.to_list(length=50)

        # Fetch last 60 days of txns ONCE for all goals (for ML ETA)
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
        tasks  = []
        for goal in goals:
            progress  = (goal.get("current", 0) / goal.get("target", 1)) * 100
            remaining = goal.get("target", 0) - goal.get("current", 0)

            try:
                deadline = datetime.fromisoformat(goal.get("deadline", datetime.utcnow().isoformat()[:10]))
            except (ValueError, TypeError):
                deadline = datetime.utcnow() + timedelta(days=365)
            days_until = (deadline - datetime.utcnow()).days

            goal_dict = {
                "id":                  str(goal["_id"]),
                "user_id":             goal["user_id"],
                "name":                goal["name"],
                "icon":                goal.get("icon", "🎯"),
                "target":              goal["target"],
                "current":             goal.get("current", 0),
                "deadline":            goal.get("deadline", ""),
                "priority":            goal.get("priority", "medium"),
                "color":               goal.get("color", "#10B981"),
                "goal_type":           goal.get("goal_type", "personal_csv"),
                "progress_percentage": round(progress, 1),
                "remaining":           remaining,
                "on_track":            remaining <= 0 or (days_until > 0 and remaining / days_until < goal["target"] / 30),
                "eta_days":            days_until if days_until > 0 else None,
                "milestones":          goal.get("milestones", []),
                # ML ETA fields (enriched below)
                "projected_completion_date": None,
                "shortfall_risk":            False,
                "ai_verified":               False,
                # Chain status (Web3)
                "chain_status":    goal.get("chain_status", "pending"),
                "badge_tx_hash":   goal.get("badge_tx_hash"),
                "badge_token_id":  goal.get("badge_token_id"),
                "wallet_address":  goal.get("wallet_address"),
                "token_uri":       goal.get("token_uri"),
                "badge_image_url": _ipfs_to_image_url(goal.get("token_uri")),
            }
            result.append(goal_dict)
            tasks.append(_enrich_goal_with_eta(goal_dict, serialized_txns))

        # Run all ML ETA calls in parallel
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return result

    except Exception as e:
        logger.error(f"[Goals] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/v1/goals ───────────────────────────────────────────────────────
@router.post("")
async def create_goal(goal: GoalCreate, db=Depends(get_database)):
    """Create a new savings goal (any type)."""
    if goal.goal_type not in GOAL_TYPES:
        raise HTTPException(status_code=400, detail=f"goal_type must be one of {GOAL_TYPES}")
    try:
        t = goal.resolved_target()
        d = goal.resolved_deadline()
        if t <= 0:
            raise HTTPException(status_code=422, detail="target / target_amount must be > 0")

        goal_doc = {
            "user_id":        goal.user_id,
            "name":           goal.name,
            "icon":           goal.icon,
            "target":         t,
            "current":        goal.current_amount or 0,
            "deadline":       d,
            "priority":       goal.priority,
            "color":          goal.color,
            "goal_type":      goal.goal_type,
            "wallet_address": goal.wallet_address,
            "salary":         goal.salary,
            "milestones":     calculate_milestones(t),
            "chain_status":   "pending",
            "badge_tx_hash":  None,
            "badge_token_id": None,
            "created_at":     datetime.utcnow(),
        }

        result = await db["goals"].insert_one(goal_doc)

        return {
            "goal_id":   str(result.inserted_id),
            "name":      goal.name,
            "target":    t,
            "goal_type": goal.goal_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/v1/goals/{goal_id}/progress ────────────────────────────────────
@router.post("/{goal_id}/progress")
async def update_goal_progress(
    goal_id: str,
    file:   UploadFile = File(..., description="Monthly/weekly transaction CSV"),
    salary: Optional[float] = Form(None, description="Monthly salary for long-term mode"),
    db=Depends(get_database),
):
    """Upload a CSV and calculate savings towards this goal."""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        content       = await file.read()
        savings_data  = _parse_csv_savings(content, salary or goal.get("salary"))
        new_savings   = savings_data["savings"]
        new_current   = goal.get("current", 0) + new_savings
        progress      = (new_current / goal["target"]) * 100

        # Update milestones
        milestones = goal.get("milestones", [])
        milestones_reached = []
        for i, ms in enumerate(milestones):
            if not ms["reached"] and new_current >= ms["amount"]:
                milestones[i]["reached"] = True
                milestones[i]["date"]    = datetime.utcnow().isoformat()
                milestones_reached.append(i + 1)

        await db["goals"].update_one(
            {"_id": ObjectId(goal_id)},
            {"$set": {
                "current":    new_current,
                "milestones": milestones,
                "updated_at": datetime.utcnow(),
            }},
        )

        is_complete = new_current >= goal["target"]

        return {
            "new_current":        round(new_current, 2),
            "savings_this_period": round(new_savings, 2),
            "total_spend":        savings_data["total_spend"],
            "mode":               savings_data["mode"],
            "progress_percentage": round(progress, 1),
            "milestones_reached": milestones_reached,
            "is_complete":        is_complete,
            "message":            "🎉 Goal complete! Ready to mint badge." if is_complete else "Progress updated.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PUT /api/v1/goals/{goal_id}/progress/manual ─────────────────────────────
@router.put("/{goal_id}/progress/manual")
async def update_progress_manual(
    goal_id: str,
    body: ManualProgressUpdate,
    db=Depends(get_database),
):
    """
    Manually update a goal's current savings.
    Used for crypto goals where there is no CSV upload.
    - mode "set":  current = amount
    - mode "add":  current += amount
    """
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        if body.mode == "set":
            new_current = body.amount
        else:
            new_current = goal.get("current", 0) + body.amount

        progress = (new_current / goal["target"]) * 100

        milestones = goal.get("milestones", [])
        for i, ms in enumerate(milestones):
            if not ms["reached"] and new_current >= ms["amount"]:
                milestones[i]["reached"] = True
                milestones[i]["date"]    = datetime.utcnow().isoformat()

        await db["goals"].update_one(
            {"_id": ObjectId(goal_id)},
            {"$set": {
                "current":    round(new_current, 4),
                "milestones": milestones,
                "updated_at": datetime.utcnow(),
            }},
        )

        is_complete = new_current >= goal["target"]

        return {
            "new_current":         round(new_current, 4),
            "progress_percentage": round(progress, 1),
            "is_complete":         is_complete,
            "message":             "🎉 Goal complete! Ready to mint badge." if is_complete else "Progress updated.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Manual progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/v1/goals/{goal_id}/complete ────────────────────────────────────
@router.post("/{goal_id}/complete")
async def complete_goal_and_mint(
    goal_id: str,
    request: CompleteGoalRequest,
    db=Depends(get_database),
):
    """
    Mark a goal complete and mint an SBT badge to the user's wallet.
    Steps: validate → PIL badge → Pinata IPFS → GoalBadgeSBT.mintBadge() → MongoDB
    """
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        if goal.get("chain_status") == "badge_minted":
            return {
                "already_minted": True,
                "badge_tx_hash":  goal.get("badge_tx_hash"),
                "message":        "Badge already minted for this goal.",
            }

        if goal.get("current", 0) < goal.get("target", 0):
            raise HTTPException(
                status_code=400,
                detail=f"Goal not yet complete. Current: {goal.get('current', 0)}, Target: {goal.get('target', 0)}"
            )

        wallet = request.wallet_address or goal.get("wallet_address")
        if not wallet:
            raise HTTPException(status_code=400, detail="wallet_address required for minting")

        if not generate_and_upload_badge or not mint_single_badge:
            raise HTTPException(status_code=501, detail="IPFS/minting services not available")

        # 1. Generate image + build + upload metadata
        token_uri = await generate_and_upload_badge(
            goal_title=goal["name"],
            goal_type=goal.get("goal_type", "personal_csv"),
            target=goal["target"],
            completed_at=datetime.utcnow().strftime("%Y-%m-%d"),
            user_wallet=wallet,
            icon=goal.get("icon", "🎯"),
        )

        # 2. Mint SBT
        mint_result = await mint_single_badge(wallet, goal["name"], token_uri)

        if not mint_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Minting failed: {mint_result.get('error')}"
            )

        # 3. Update MongoDB
        await db["goals"].update_one(
            {"_id": ObjectId(goal_id)},
            {"$set": {
                "chain_status":   "badge_minted",
                "badge_tx_hash":  mint_result["tx_hash"],
                "token_uri":      token_uri,
                "wallet_address": wallet,
                "completed_at":   datetime.utcnow(),
            }},
        )

        return {
            "success":        True,
            "badge_tx_hash":  mint_result["tx_hash"],
            "token_uri":      token_uri,
            "wallet_address": wallet,
            "message":        f"🎉 SBT badge minted for '{goal['name']}'!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Complete+Mint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PUT /api/v1/goals/{goal_id}/contribute ───────────────────────────────────
@router.put("/{goal_id}/contribute")
async def contribute_to_goal(goal_id: str, contribution: GoalContribute, db=Depends(get_database)):
    """Add funds to a goal."""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        new_current = goal.get("current", 0) + contribution.amount
        progress    = (new_current / goal["target"]) * 100

        milestones = goal.get("milestones", [])
        milestones_reached = []
        for i, ms in enumerate(milestones):
            if not ms["reached"] and new_current >= ms["amount"]:
                milestones[i]["reached"] = True
                milestones[i]["date"]    = datetime.utcnow().isoformat()
                milestones_reached.append(i + 1)

        await db["goals"].update_one(
            {"_id": ObjectId(goal_id)},
            {"$set": {
                "current":    new_current,
                "milestones": milestones,
                "updated_at": datetime.utcnow(),
            }},
        )

        is_complete = new_current >= goal["target"]
        xp_earned   = 10 + (25 * len(milestones_reached)) + (100 if is_complete else 0)

        return {
            "new_current":         new_current,
            "progress_percentage": round(progress, 1),
            "milestones_reached":  milestones_reached,
            "is_complete":         is_complete,
            "xp_earned":           xp_earned,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] Contribute error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/v1/goals/{goal_id}/eta ──────────────────────────────────────────
@router.get("/{goal_id}/eta")
async def get_goal_eta(goal_id: str, db=Depends(get_database)):
    """Get estimated time to reach goal (standalone endpoint)."""
    try:
        goal = await db["goals"].find_one({"_id": ObjectId(goal_id)})
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        deadline   = datetime.fromisoformat(goal.get("deadline", datetime.utcnow().isoformat()[:10]))
        days_until = (deadline - datetime.utcnow()).days
        remaining  = goal["target"] - goal.get("current", 0)

        if remaining <= 0:
            return {"eta_days": 0, "days_until_deadline": days_until, "on_track": True, "message": "Goal completed! 🎉"}

        created    = goal.get("created_at", datetime.utcnow())
        elapsed    = max(1, (datetime.utcnow() - created).days)
        avg_daily  = goal.get("current", 0) / elapsed
        eta_days   = int(remaining / avg_daily) if avg_daily > 0 else None

        return {
            "eta_days":            eta_days,
            "days_until_deadline": days_until,
            "on_track":            eta_days is not None and eta_days <= days_until,
            "message":             "On track! 🚀" if eta_days and eta_days <= days_until else "Need to increase savings 📈",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Goals] ETA error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── DELETE /api/v1/goals/{goal_id} ───────────────────────────────────────────
@router.delete("/{goal_id}")
async def delete_goal(goal_id: str, db=Depends(get_database)):
    """Delete a goal."""
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
