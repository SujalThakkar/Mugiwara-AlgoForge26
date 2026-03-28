"""
Escrow Routes — Group Escrow Pool Management
Backend ledger for GroupEscrow smart contract pools.
Provides invite links, member tracking, pledge management, and SBT batch minting.

Author: Aryan Lomte
Version: 2.0.0 (Goals 2.0 — with pledges + enriched responses)
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import logging
import secrets

from api.database import get_database
from api.services.ipfs_service import generate_and_upload_badge
from api.services.minting_service import batch_mint_badges
from api.routes.savings import _compute_gross_savings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/escrow", tags=["Escrow"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class EscrowPoolCreate(BaseModel):
    creator_user_id:   str
    creator_wallet:    str
    name:              str
    target_amount:     float             # in POL (for escrow) or ₹ (for display)
    target_currency:   str = "POL"       # "POL" | "INR"
    deadline:          str               # ISO date string
    max_members:       int = 10


class MemberJoin(BaseModel):
    user_id:        str
    wallet_address: str
    pledge_amount:  float = 0.0          # ← NEW: what they commit to save
    display_name:   str = ""             # optional display name


class BatchMintRequest(BaseModel):
    """Called by admin/backend after on-chain completePool to mint SBTs."""
    pool_id: str


def _member_status(saved: float, pledged: float, joined_at: str, target_date: str) -> str:
    """Compute member status: fulfilled / on_track / behind."""
    if pledged <= 0:
        return "on_track"
    if saved >= pledged:
        return "fulfilled"

    # Pace check: is saved_amount > 20% below expected pace?
    try:
        joined = datetime.fromisoformat(joined_at)
        deadline = datetime.fromisoformat(target_date)
        now = datetime.utcnow()
        total_days = max(1, (deadline - joined).days)
        elapsed_days = max(1, (now - joined).days)
        expected = pledged * (elapsed_days / total_days)
        if saved < expected * 0.8:  # more than 20% behind pace
            return "behind"
    except Exception:
        pass

    return "on_track"


# ── POST /api/v1/escrow ───────────────────────────────────────────────────────
@router.post("")
async def create_escrow_pool(pool: EscrowPoolCreate, db=Depends(get_database)):
    """
    Create a group escrow pool.
    Returns a unique invite_code for sharing.
    The on-chain pool creation tx is done by the frontend separately.
    """
    try:
        invite_code = secrets.token_urlsafe(8)

        pool_doc = {
            "creator_user_id":  pool.creator_user_id,
            "creator_wallet":   pool.creator_wallet,
            "name":             pool.name,
            "target_amount":    pool.target_amount,
            "target_currency":  pool.target_currency,
            "deadline":         pool.deadline,
            "max_members":      pool.max_members,
            "invite_code":      invite_code,
            "members": [
                {
                    "user_id":      pool.creator_user_id,
                    "wallet":       pool.creator_wallet,
                    "display_name": "",
                    "pledge_amount": 0.0,
                    "joined_at":    datetime.utcnow().isoformat(),
                }
            ],
            "chain_pool_id":    None,
            "chain_status":     "pending",
            "badge_tx_hash":    None,
            "created_at":       datetime.utcnow(),
        }

        result   = await db["escrow_pools"].insert_one(pool_doc)
        pool_id  = str(result.inserted_id)

        return {
            "pool_id":     pool_id,
            "invite_code": invite_code,
            "invite_url":  f"/escrow/join/{pool_id}",
            "name":        pool.name,
            "target":      pool.target_amount,
            "currency":    pool.target_currency,
            "deadline":    pool.deadline,
        }

    except Exception as e:
        logger.error(f"[Escrow] Create error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/v1/escrow/{pool_id} ──────────────────────────────────────────────
@router.get("/{pool_id}")
async def get_escrow_pool(pool_id: str, db=Depends(get_database)):
    """
    Get enriched pool details + member list with savings data.
    Each member gets saved_amount = gross_savings from GET /savings/{user_id}.
    """
    try:
        pool = await db["escrow_pools"].find_one({"_id": ObjectId(pool_id)})
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")

        target_date = pool.get("deadline", "")
        members_raw = pool.get("members", [])

        # Enrich each member with saved_amount from gross savings
        enriched_members = []
        for m in members_raw:
            user_id = m.get("user_id", "")
            pledge = m.get("pledge_amount", 0)

            # Compute gross savings for this member
            try:
                savings_data = await _compute_gross_savings(user_id, db)
                saved = savings_data.get("gross_savings", 0)
            except Exception:
                saved = 0

            # Get display name from users collection if not set
            display_name = m.get("display_name", "")
            if not display_name:
                user_doc = await db["users"].find_one({"_id": user_id})
                display_name = user_doc.get("name", user_id[:8]) if user_doc else user_id[:8]

            # Avatar initials
            parts = display_name.split()
            initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else parts[0][-1])).upper() if parts else "??"

            status = _member_status(saved, pledge, m.get("joined_at", ""), target_date)

            enriched_members.append({
                "user_id":         user_id,
                "wallet":          m.get("wallet", ""),
                "display_name":    display_name,
                "avatar_initials": initials,
                "joined_at":       m.get("joined_at", ""),
                "pledge_amount":   pledge,
                "saved_amount":    round(saved, 2),
                "status":          status,
            })

        total_pledged = sum(m["pledge_amount"] for m in enriched_members)
        total_saved   = sum(m["saved_amount"] for m in enriched_members)
        target_amount = pool["target_amount"]
        completion_pct = round((total_saved / target_amount) * 100, 1) if target_amount > 0 else 0
        is_complete = all(m["status"] == "fulfilled" for m in enriched_members) and len(enriched_members) > 0

        return {
            "pool_id":         str(pool["_id"]),
            "name":            pool["name"],
            "target_amount":   target_amount,
            "target_currency": pool.get("target_currency", "POL"),
            "target_date":     target_date,
            "max_members":     pool.get("max_members", 10),
            "member_count":    len(enriched_members),
            "members":         enriched_members,
            "total_pledged":   round(total_pledged, 2),
            "total_saved":     round(total_saved, 2),
            "completion_pct":  completion_pct,
            "is_complete":     is_complete,
            "invite_code":     pool.get("invite_code"),
            "chain_pool_id":   pool.get("chain_pool_id"),
            "chain_status":    pool.get("chain_status", "pending"),
            "badge_tx_hash":   pool.get("badge_tx_hash"),
            "creator_wallet":  pool.get("creator_wallet"),
            "creator_user_id": pool.get("creator_user_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Escrow] Get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/v1/escrow/{pool_id}/join ───────────────────────────────────────
@router.post("/{pool_id}/join")
async def join_escrow_pool(pool_id: str, member: MemberJoin, db=Depends(get_database)):
    """Register a new member joining the pool via invite link."""
    try:
        pool = await db["escrow_pools"].find_one({"_id": ObjectId(pool_id)})
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")

        members = pool.get("members", [])

        # Check already joined
        if any(m["wallet"].lower() == member.wallet_address.lower() for m in members):
            return {"already_member": True, "pool_id": pool_id}

        # Check capacity
        if len(members) >= pool.get("max_members", 10):
            raise HTTPException(status_code=400, detail="Pool is full")

        new_member = {
            "user_id":       member.user_id,
            "wallet":        member.wallet_address,
            "display_name":  member.display_name,
            "pledge_amount": member.pledge_amount,
            "joined_at":     datetime.utcnow().isoformat(),
        }

        await db["escrow_pools"].update_one(
            {"_id": ObjectId(pool_id)},
            {"$push": {"members": new_member}},
        )

        return {
            "joined":       True,
            "pool_id":      pool_id,
            "pool_name":    pool["name"],
            "member_count": len(members) + 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Escrow] Join error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── PUT /api/v1/escrow/{pool_id}/chain-link ───────────────────────────────────
@router.put("/{pool_id}/chain-link")
async def link_chain_pool(pool_id: str, chain_pool_id: int, db=Depends(get_database)):
    """After frontend calls createPool on-chain, link the on-chain poolId here."""
    try:
        await db["escrow_pools"].update_one(
            {"_id": ObjectId(pool_id)},
            {"$set": {"chain_pool_id": chain_pool_id, "chain_status": "funded"}},
        )
        return {"linked": True, "chain_pool_id": chain_pool_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/v1/escrow/{pool_id}/complete ───────────────────────────────────
@router.post("/{pool_id}/complete")
async def complete_escrow_and_mint(pool_id: str, db=Depends(get_database)):
    """
    Called after on-chain completePool() succeeds.
    Uploads IPFS badge metadata and batch-mints SBTs to all member wallets.
    """
    try:
        pool = await db["escrow_pools"].find_one({"_id": ObjectId(pool_id)})
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")

        if pool.get("chain_status") == "completed":
            return {
                "already_completed": True,
                "badge_tx_hash":     pool.get("badge_tx_hash"),
            }

        members         = pool.get("members", [])
        member_wallets  = [m["wallet"] for m in members if m.get("wallet")]

        if not member_wallets:
            raise HTTPException(status_code=400, detail="No member wallets found")

        # 1. Generate image + build + upload metadata (full pipeline)
        token_uri = await generate_and_upload_badge(
            goal_title=pool["name"],
            goal_type="group_escrow",
            target=pool["target_amount"],
            completed_at=datetime.utcnow().strftime("%Y-%m-%d"),
            extra_attrs=[{"trait_type": "Members", "value": str(len(member_wallets))}],
        )

        # 2. Batch mint (max 20 per tx — split if needed)
        all_tx_hashes = []
        for i in range(0, len(member_wallets), 20):
            chunk  = member_wallets[i:i + 20]
            result = await batch_mint_badges(chunk, pool["name"], token_uri)
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=f"Batch mint failed: {result.get('error')}")
            all_tx_hashes.append(result["tx_hash"])

        # 3. Update pool status
        await db["escrow_pools"].update_one(
            {"_id": ObjectId(pool_id)},
            {"$set": {
                "chain_status":  "completed",
                "badge_tx_hash": all_tx_hashes[0],
                "completed_at":  datetime.utcnow(),
            }},
        )

        return {
            "success":        True,
            "badges_minted":  len(member_wallets),
            "tx_hashes":      all_tx_hashes,
            "token_uri":      token_uri,
            "message":        f"🎉 {len(member_wallets)} SBT badges minted for '{pool['name']}'!",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Escrow] Complete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/v1/escrow/user/{user_id} ────────────────────────────────────────
@router.get("/user/{user_id}")
async def get_user_pools(user_id: str, db=Depends(get_database)):
    """Get all escrow pools a user is part of (summary view)."""
    try:
        cursor = db["escrow_pools"].find({
            "members": {"$elemMatch": {"user_id": user_id}}
        })
        pools = await cursor.to_list(length=20)

        return [
            {
                "pool_id":       str(p["_id"]),
                "name":          p["name"],
                "target_amount": p["target_amount"],
                "currency":      p.get("target_currency", "POL"),
                "deadline":      p["deadline"],
                "member_count":  len(p.get("members", [])),
                "chain_status":  p.get("chain_status", "pending"),
                "badge_tx_hash": p.get("badge_tx_hash"),
                "is_creator":    p.get("creator_user_id") == user_id,
            }
            for p in pools
        ]

    except Exception as e:
        logger.error(f"[Escrow] User pools error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
