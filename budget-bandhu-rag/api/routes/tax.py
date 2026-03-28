"""
api/routes/tax.py — 80C Auto-Tracker
Scans all FY transactions for ELSS/PPF/NPS/LIC keywords → computes tax saved.

Author: BudgetBandhu
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import logging, re

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tax", tags=["Tax"])

# ── 80C instrument keywords (case-insensitive) ────────────────────────────
SECTION_80C_KEYWORDS = {
    "ELSS":   ["elss", "tax saver fund", "tax saving fund", "equity linked"],
    "PPF":    ["ppf", "public provident", "provident fund"],
    "EPF":    ["epf", "employee provident", "pf contribution"],
    "NPS":    ["nps", "national pension", "atal pension", "apy"],
    "LIC":    ["lic", "life insurance", "jeevan", "hdfc life", "sbi life",
               "icici prulife", "bajaj allianz life", "kotak life"],
    "ULIP":   ["ulip"],
    "FD":     ["tax saver fd", "80c fd", "5 year fd"],
    "NSC":    ["nsc", "national savings certificate"],
    "SCSS":   ["scss", "senior citizen saving"],
    "Sukanya":["sukanya", "ssya"],
    "Tuition":["tuition fee", "school fee", "college fee"],
}

LIMIT_80C = 150000   # ₹1.5 Lakh per FY

# Standard tax slabs (FY 2025-26 new regime approximation)
def _get_slab_rate(annual_income: float) -> float:
    if annual_income <= 300000:    return 0.0
    elif annual_income <= 700000:  return 0.05
    elif annual_income <= 1000000: return 0.10
    elif annual_income <= 1200000: return 0.15
    elif annual_income <= 1500000: return 0.20
    else:                          return 0.30


@router.get("/{user_id}/80c")
async def get_80c_tracker(user_id: str, db=Depends(get_database)):
    """
    Scan all FY transactions for 80C-eligible investments.
    Returns: total_invested, breakdown by instrument, tax_saved, remaining.
    """
    try:
        # Current FY: April 1 to March 31
        now = datetime.utcnow()
        fy_start = f"{now.year - 1 if now.month < 4 else now.year}-04-01"
        fy_end   = f"{now.year if now.month >= 4 else now.year - 1}-03-31"

        # Get user income for slab rate
        user = await db["users"].find_one({"_id": user_id})
        annual_income = (user.get("income", 50000) if user else 50000) * 12

        # Fetch all FY transactions
        cursor = db["transactions"].find({
            "user_id": user_id,
            "type": "debit",
            "date": {"$gte": fy_start, "$lte": fy_end}
        })
        txns = await cursor.to_list(length=5000)

        # Scan descriptions for 80C keywords
        breakdown = {}
        for txn in txns:
            desc = (txn.get("description", "") + " " + txn.get("category", "")).lower()
            for instrument, keywords in SECTION_80C_KEYWORDS.items():
                if any(kw in desc for kw in keywords):
                    if instrument not in breakdown:
                        breakdown[instrument] = {"amount": 0, "count": 0, "transactions": []}
                    breakdown[instrument]["amount"] += txn.get("amount", 0)
                    breakdown[instrument]["count"]  += 1
                    breakdown[instrument]["transactions"].append({
                        "date": txn.get("date", ""),
                        "description": txn.get("description", ""),
                        "amount": txn.get("amount", 0)
                    })
                    break  # each transaction counts under one instrument

        total_invested = round(sum(v["amount"] for v in breakdown.values()), 2)
        eligible_invested = min(total_invested, LIMIT_80C)
        remaining_limit   = max(0, LIMIT_80C - eligible_invested)
        slab_rate         = _get_slab_rate(annual_income)
        tax_saved         = round(eligible_invested * slab_rate, 2)
        potential_saving  = round(remaining_limit * slab_rate, 2)

        # Best recommendation
        recommendations = []
        if remaining_limit > 0:
            if "ELSS" not in breakdown:
                recommendations.append({
                    "instrument": "ELSS",
                    "reason": "3-year lock-in (shortest), market-linked returns avg 12-15%. Invest ₹{:,.0f} more.".format(remaining_limit),
                    "potential_tax_saving": round(remaining_limit * slab_rate, 2)
                })
            if "NPS" not in breakdown and annual_income > 500000:
                recommendations.append({
                    "instrument": "NPS (80CCD 1B)",
                    "reason": "Extra ₹50,000 deduction over 80C limit under Sec 80CCD(1B).",
                    "potential_tax_saving": round(50000 * slab_rate, 2)
                })

        return {
            "fy": f"FY {fy_start[:4]}-{fy_end[:4]}",
            "user_id": user_id,
            "total_invested": total_invested,
            "eligible_amount": eligible_invested,
            "limit_80c": LIMIT_80C,
            "remaining_limit": remaining_limit,
            "percentage_used": round(eligible_invested / LIMIT_80C * 100, 1),
            "slab_rate": slab_rate,
            "tax_saved": tax_saved,
            "potential_additional_saving": potential_saving,
            "breakdown": {
                k: {"amount": round(v["amount"], 2), "count": v["count"],
                    "transactions": v["transactions"][:5]}  # show last 5
                for k, v in breakdown.items()
            },
            "recommendations": recommendations[:3]
        }

    except Exception as e:
        logger.error(f"[Tax80C] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
