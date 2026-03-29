"""
api/routes/bills.py — Upcoming Bills CRUD (Atlas DB)
Chat → Dashboard sync: Bandhu writes bills here, frontend reads them.

Author: BudgetBandhu
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bills", tags=["Bills"])


class BillCreate(BaseModel):
    title: str
    amount: float
    due_date: str          # "YYYY-MM-DD"
    category: Optional[str] = "Other"
    recurring: Optional[bool] = False
    notes: Optional[str] = None


def _enrich_bill(bill: dict) -> dict:
    """Add computed fields: days_until_due, status, urgency."""
    try:
        due = datetime.strptime(bill["due_date"][:10], "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        days = (due - today).days
    except Exception:
        days = 999

    if days < 0:
        status = "overdue"
    elif days <= 3:
        status = "due-soon"
    elif days <= 7:
        status = "upcoming"
    else:
        status = "future"

    return {
        **bill,
        "id": str(bill.get("_id", bill.get("id", ""))),
        "days_until_due": days,
        "status": status,
    }


@router.get("/{user_id}")
async def get_bills(user_id: str, db=Depends(get_database)):
    """Get all upcoming bills for a user, sorted by due date."""
    try:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        cursor = db["bills"].find(
            {"user_id": user_id, "due_date": {"$gte": today_str}}
        ).sort("due_date", 1)
        bills = await cursor.to_list(length=50)

        enriched = [_enrich_bill({**b, "_id": str(b["_id"])}) for b in bills]
        return enriched
    except Exception as e:
        logger.error(f"[Bills] GET error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}")
async def create_bill(user_id: str, bill: BillCreate, db=Depends(get_database)):
    """Create a new bill (called by chatbot or UI)."""
    try:
        doc = {
            "user_id": user_id,
            "title": bill.title,
            "amount": bill.amount,
            "due_date": bill.due_date,
            "category": bill.category or "Other",
            "recurring": bill.recurring or False,
            "notes": bill.notes,
            "created_at": datetime.utcnow().isoformat(),
            "source": "chat",
        }
        result = await db["bills"].insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        return {"status": "created", "bill": _enrich_bill(doc)}
    except Exception as e:
        logger.error(f"[Bills] POST error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}/{bill_id}")
async def delete_bill(user_id: str, bill_id: str, db=Depends(get_database)):
    """Remove a bill."""
    try:
        from bson import ObjectId
        result = await db["bills"].delete_one(
            {"_id": ObjectId(bill_id), "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Bill not found")
        return {"status": "deleted", "bill_id": bill_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bills] DELETE error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/summary")
async def get_bills_summary(user_id: str, db=Depends(get_database)):
    """Total due, overdue count, next bill — for dashboard header."""
    try:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        cursor = db["bills"].find(
            {"user_id": user_id, "due_date": {"$gte": today_str}}
        ).sort("due_date", 1)
        bills = await cursor.to_list(length=50)

        total_due = sum(b.get("amount", 0) for b in bills)
        overdue = [b for b in bills if b["due_date"] < today_str]
        return {
            "total_bills": len(bills),
            "total_due": round(total_due, 2),
            "overdue_count": len(overdue),
            "next_bill": _enrich_bill({**bills[0], "_id": str(bills[0]["_id"])}) if bills else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
