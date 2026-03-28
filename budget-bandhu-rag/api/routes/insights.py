"""
Insights/Analytics Routes — Multi-source insight aggregator.
Pulls from: anomalies in DB, forecast cache, category trends.

BudgetBandhu API
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
import logging

from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


async def _source_a_anomalies(db, user_id: str) -> List[dict]:
    """Recent anomaly-flagged transactions → insight cards."""
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    cursor = db["transactions"].find({
        "user_id": user_id,
        "is_anomaly": True,
        "created_at": {"$gte": seven_days_ago},
    }).sort("anomaly_score", -1).limit(5)
    txns = await cursor.to_list(length=5)

    cards = []
    for i, t in enumerate(txns):
        sev = str(t.get("anomaly_severity", "medium")).lower()
        if sev not in SEVERITY_ORDER:
            sev = "medium"
        cards.append({
            "id": f"ins_anom_{i}",
            "type": "anomaly",
            "title": f"Unusual transaction: ₹{t.get('amount', 0):,.0f} on {t.get('description', 'Unknown')}",
            "description": t.get("anomaly_reason") or "This transaction looks different from your usual pattern.",
            "severity": sev,
            "category": t.get("category", "Other"),
            "transaction_id": str(t.get("_id", "")),
        })
    return cards


async def _source_b_forecast(db, user_id: str) -> List[dict]:
    """Forecast cache signals → insight cards."""
    cards = []
    try:
        cache = await db["forecast_cache"].find_one({"user_id": user_id})
        if not cache or not cache.get("forecast"):
            return cards
        fc = cache["forecast"]
        predicted = fc.get("predicted_spending", 0)
        savings = fc.get("predicted_savings", 0)
        summary = fc.get("monthly_summary", {})
        vs_last = summary.get("vs_last_month", 0)

        if vs_last > 10:
            cards.append({
                "id": "ins_fc_warn",
                "type": "warning",
                "title": f"Spending projected to rise {vs_last:.0f}% vs last month",
                "description": f"Your projected spend of ₹{predicted:,.0f} is higher than last month. Review non-essential categories.",
                "severity": "medium",
                "action": "View Budget",
                "action_url": "/budget",
            })
        if vs_last < -5:
            cards.append({
                "id": "ins_fc_good",
                "type": "forecast",
                "title": "Savings trending up!",
                "description": f"You're projected to save ₹{savings:,.0f} this month — {abs(vs_last):.0f}% better than last month.",
                "severity": "low",
            })
        top_cat = summary.get("top_category")
        if top_cat:
            cards.append({
                "id": "ins_fc_top",
                "type": "budget_alert",
                "title": f"{top_cat} is your biggest projected expense",
                "description": f"Consider reviewing your {top_cat} budget allocation.",
                "severity": "low",
                "category": top_cat,
                "action": "View Budget",
                "action_url": "/budget",
            })
    except Exception as e:
        logger.warning(f"[Insights] Forecast source error: {e}")
    return cards


async def _source_c_trends(db, user_id: str) -> List[dict]:
    """7-day vs prior-7-day category trend → insight cards."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    this_cursor = db["transactions"].find({
        "user_id": user_id, "type": "debit",
        "created_at": {"$gte": week_ago},
    })
    prev_cursor = db["transactions"].find({
        "user_id": user_id, "type": "debit",
        "created_at": {"$gte": two_weeks_ago, "$lt": week_ago},
    })

    this_txns = await this_cursor.to_list(length=500)
    prev_txns = await prev_cursor.to_list(length=500)

    this_spend: Dict[str, float] = defaultdict(float)
    prev_spend: Dict[str, float] = defaultdict(float)
    for t in this_txns:
        this_spend[t.get("category", "Other")] += t.get("amount", 0)
    for t in prev_txns:
        prev_spend[t.get("category", "Other")] += t.get("amount", 0)

    cards = []
    for cat, amt in this_spend.items():
        prev_amt = prev_spend.get(cat, 0)
        if prev_amt > 0:
            pct_change = ((amt - prev_amt) / prev_amt) * 100
            if pct_change > 30:
                cards.append({
                    "id": f"ins_trend_{cat}",
                    "type": "warning",
                    "title": f"{cat} increased {pct_change:.0f}% this week",
                    "description": f"You spent ₹{amt:,.0f} on {cat} this week vs ₹{prev_amt:,.0f} last week. Consider delaying non-essential purchases.",
                    "severity": "medium" if pct_change < 60 else "high",
                    "category": cat,
                    "action": "View Budget",
                    "action_url": "/budget",
                })
    cards.sort(key=lambda c: c.get("severity", "low") == "high", reverse=True)
    return cards


async def _compute_save_potential(db, user_id: str) -> float:
    """Estimate weekly save potential from budget overspend."""
    budget = await db["budgets"].find_one({"user_id": user_id})
    if not budget:
        return 0
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    cursor = db["transactions"].find({
        "user_id": user_id, "type": "debit",
        "created_at": {"$gte": thirty_days_ago},
    })
    txns = await cursor.to_list(length=500)
    actual: Dict[str, float] = defaultdict(float)
    for t in txns:
        actual[t.get("category", "Other")] += t.get("amount", 0)

    total = 0
    for alloc in budget.get("allocations", []):
        cat = alloc["category"]
        allocated = alloc.get("allocated", 0)
        spent = actual.get(cat, 0)
        if spent > allocated:
            total += spent - allocated
    return round(total, 2)


async def _build_insights(db, user_id: str) -> dict:
    """Aggregate insights from 3 sources in parallel."""
    results = await asyncio.gather(
        _source_a_anomalies(db, user_id),
        _source_b_forecast(db, user_id),
        _source_c_trends(db, user_id),
        _compute_save_potential(db, user_id),
        return_exceptions=True,
    )

    all_cards = []
    for r in results[:3]:
        if isinstance(r, list):
            all_cards.extend(r)

    # Deduplicate by category (keep highest severity)
    seen_cats = {}
    deduped = []
    for card in all_cards:
        cat = card.get("category")
        if cat and cat in seen_cats:
            existing = seen_cats[cat]
            if SEVERITY_ORDER.get(card.get("severity", "low"), 2) < SEVERITY_ORDER.get(existing.get("severity", "low"), 2):
                deduped.remove(existing)
                deduped.append(card)
                seen_cats[cat] = card
        else:
            deduped.append(card)
            if cat:
                seen_cats[cat] = card

    # Sort by severity, limit to 5
    deduped.sort(key=lambda c: SEVERITY_ORDER.get(c.get("severity", "low"), 2))
    insights = deduped[:5]

    save_potential = results[3] if not isinstance(results[3], Exception) else 0

    return {
        "insights": insights,
        "weekly_summary": {
            "save_potential": save_potential,
            "message": f"Save up to ₹{save_potential:,.0f}/month! 🔥" if save_potential > 0 else "Your spending looks balanced! ✅",
        },
    }


# ── Legacy analytics endpoint (updated inline) ───────────────────────────

@router.get("/{user_id}", response_model=dict)
async def get_analytics(user_id: str, db=Depends(get_database)):
    """
    Get spending insights for a user.
    Returns category breakdown + ML-powered insight cards from 3 sources.
    """
    try:
        # Legacy aggregation
        cursor = db["transactions"].find(
            {"user_id": user_id, "type": "debit"}
        ).limit(200)

        txns = []
        async for doc in cursor:
            txns.append({
                "amount": doc["amount"],
                "category": doc.get("category", "Other"),
                "description": doc.get("description", ""),
            })

        category_totals = {}
        total_spend = 0
        for txn in txns:
            category = txn.get("category", "Other")
            amount = abs(txn.get("amount", 0))
            category_totals[category] = category_totals.get(category, 0) + amount
            total_spend += amount

        # Build new insights
        insights_data = await _build_insights(db, user_id)

        return {
            "success": True,
            "total_spend": round(total_spend, 2),
            "category_breakdown": {k: round(v, 2) for k, v in category_totals.items()},
            **insights_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Dedicated insights endpoint ──────────────────────────────────────────

@router.get("/{user_id}/insights", response_model=dict)
async def get_insights(user_id: str, db=Depends(get_database)):
    """
    Dedicated insights endpoint. Returns ML-powered insight cards
    aggregated from anomalies, forecasts, and category trends.
    """
    try:
        return await _build_insights(db, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
