from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from api.schemas import (
    CategorizeRequest, AnomalyRequest, ForecastRequest, UserFinancialState,
    TransactionForecastRequest, GoalEtaRequest
)
from intelligence.policy_learner import UserFinancialState as PolicyState
from intelligence.ml_pipeline import BudgetBandhuMLPipeline
import time
from collections import defaultdict
from datetime import datetime, timedelta, date

router   = APIRouter(prefix="/ml", tags=["ML Models"])
pipeline = BudgetBandhuMLPipeline()


def get_pipeline() -> BudgetBandhuMLPipeline:
    return pipeline


# ── Full CSV pipeline ─────────────────────────────────────────────────────
@router.post(
    "/analyze",
    summary="Run full 4-model ML pipeline on uploaded transaction CSV",
)
async def process_csv(
    file: UploadFile = File(..., description="UPI/bank transaction CSV"),
    user_id: str     = Form(default="anonymous"),
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files accepted.")
    try:
        csv_bytes = await file.read()
        result    = await pl.process_csv(csv_bytes, user_id)
        if "error" in result:
            raise HTTPException(status_code=422, detail=result["error"])
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


# ── Categorization ────────────────────────────────────────────────────────
@router.post(
    "/categorize",
    summary="Categorise one or more UPI transaction descriptions",
)
async def categorize(
    req: CategorizeRequest,
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    if not req.descriptions:
        raise HTTPException(status_code=400, detail="descriptions list is empty.")
    if len(req.descriptions) > 10_000:
        raise HTTPException(status_code=400, detail="Max 10,000 descriptions per call.")
    try:
        print(">>> INPUT DESCRIPTIONS:", req.descriptions)
        t0      = time.time()
        results = pl.categorizer.categorize_batch(req.descriptions)
        print(">>> RAW MODEL OUTPUT:", [r.dict() for r in results])
        elapsed = round((time.time() - t0) * 1000, 1)
        return {
            "results":        [r.dict() for r in results],
            "count":          len(results),
            "processing_ms":  elapsed,
            "model_active":   pl.categorizer.is_loaded(),
        }
    except Exception as e:
        print(">>> CATEGORIZE ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── Anomaly detection ─────────────────────────────────────────────────────
@router.post(
    "/anomalies",
    summary="Detect spending anomalies in a transaction batch",
)
async def detect_anomalies(
    req: AnomalyRequest,
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    try:
        txns  = [t.dict() for t in req.transactions]
        hist  = [t.dict() for t in req.history]
        t0    = time.time()
        anoms = pl.anomaly_detector.detect_batch(txns, hist)
        return {
            "anomalies":       [a.dict() for a in anoms],
            "total":           len(anoms),
            "flagged":         sum(1 for a in anoms if a.is_anomaly),
            "high_severity":   sum(1 for a in anoms if a.severity == "HIGH"),
            "processing_ms":   round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Forecast ──────────────────────────────────────────────────────────────
@router.post(
    "/forecast",
    summary="Forecast spending for next N days using trained BiLSTM",
)
async def forecast(
    req: ForecastRequest,
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    if req.days_ahead < 1 or req.days_ahead > 90:
        raise HTTPException(status_code=400,
                            detail="days_ahead must be between 1 and 90.")
    try:
        history = [d.dict() for d in req.daily_history]
        t0      = time.time()
        result  = pl.forecaster.forecast(history, req.days_ahead)
        return {
            **result.dict(),
            "processing_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Budget optimisation ───────────────────────────────────────────────────
@router.post(
    "/budget/optimize",
    summary="Get Q-Learning adaptive budget recommendation",
)
async def optimize_budget(
    req: UserFinancialState,
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    try:
        state = PolicyState(
            monthly_income       = req.monthly_income,
            current_savings_rate = req.current_savings_rate,
            goal_progress        = req.goal_progress,
            category_spend       = req.category_spend,
            budget_allocations   = req.budget_allocations,
        )
        t0  = time.time()
        rec = pl.policy_learner.get_recommendation(state)
        return {
            **rec.dict(),
            "processing_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Forecast from raw transactions ────────────────────────────────────────
@router.post(
    "/forecast-from-transactions",
    summary="Forecast spending from raw transaction list (used by dashboard)",
)
async def forecast_from_transactions(
    req: TransactionForecastRequest,
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    """Convert raw transactions → daily spend matrix → run forecaster → return frontend-shaped response."""
    try:
        t0 = time.time()
        txns = req.transactions
        income = req.income

        # Build daily spend matrix from raw transactions
        daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for t in txns:
            txn_type = str(t.get("type", t.get("transaction_type", "debit"))).lower()
            if txn_type in {"credit", "cr", "received", "salary"}:
                continue
            raw_date = str(t.get("date", ""))[:10]
            if not raw_date:
                continue
            cat = t.get("category", "Other")
            daily[raw_date][cat] += float(t.get("amount", 0))

        daily_history = [
            {"date": d, "category_amounts": dict(cats)}
            for d, cats in sorted(daily.items())
        ]

        if len(daily_history) < 3:
            return {"predicted_spending": 0, "predicted_savings": 0, "confidence": 0,
                    "forecast_7d": [], "monthly_summary": None, "processing_ms": 0}

        result = pl.forecaster.forecast(daily_history, 7)

        # Compute last-month actual spend for vs_last_month
        now = datetime.utcnow()
        last_month_start = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        last_month_spend = sum(
            float(t.get("amount", 0)) for t in txns
            if str(t.get("type", "debit")).lower() not in {"credit", "cr", "received", "salary"}
            and str(t.get("date", ""))[:7] == last_month_start.strftime("%Y-%m")
        )

        predicted_spending = result.total_predicted_30d
        predicted_savings = max(0, round(income - predicted_spending, 2))
        vs_last_month = round(((predicted_spending - last_month_spend) / (last_month_spend + 1)) * 100, 1) if last_month_spend > 0 else 0

        # Top category from forecast
        top_cat = max(result.forecast_by_category, key=result.forecast_by_category.get) if result.forecast_by_category else "Other"

        # Build 7-day forecast array
        today = now.date()
        forecast_7d = []
        for i, day_data in enumerate(result.forecast_by_day[:7]):
            d = today + timedelta(days=i + 1)
            forecast_7d.append({
                "date": d.isoformat(),
                "predicted_amount": round(sum(day_data.values()), 2),
            })

        return {
            "predicted_spending": predicted_spending,
            "predicted_savings": predicted_savings,
            "confidence": result.confidence,
            "forecast_7d": forecast_7d,
            "monthly_summary": {
                "projected_total": predicted_spending,
                "vs_last_month": vs_last_month,
                "top_category": top_cat,
            },
            "processing_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Goal ETA ──────────────────────────────────────────────────────────────
@router.post(
    "/goal-eta",
    summary="Estimate time-to-goal from transaction savings rate",
)
async def goal_eta(req: GoalEtaRequest):
    """Compute ETA for a savings goal based on recent transaction history."""
    try:
        t0 = time.time()
        goal = req.goal
        txns = req.transactions

        target_amount = float(goal.get("target_amount", 0))
        current_amount = float(goal.get("current_amount", 0))
        target_date_str = str(goal.get("target_date", ""))

        remaining = max(0, target_amount - current_amount)

        # Compute monthly net savings from last 60 days
        total_credit = sum(float(t.get("amount", 0)) for t in txns
                           if str(t.get("type", t.get("transaction_type", "debit"))).lower() in {"credit", "cr", "received", "salary"})
        total_debit = sum(float(t.get("amount", 0)) for t in txns
                          if str(t.get("type", t.get("transaction_type", "debit"))).lower() not in {"credit", "cr", "received", "salary"})

        # Scale to monthly (txns cover ~60 days = 2 months)
        months_covered = max(1, len(set(str(t.get("date", ""))[:7] for t in txns if t.get("date"))))
        monthly_savings = max(0, (total_credit - total_debit) / months_covered)

        # Fallback: if no credits, estimate savings as 20% of debit
        if monthly_savings <= 0:
            monthly_savings = total_debit * 0.2 / max(months_covered, 1)

        monthly_needed = remaining / max(1, 12)  # default 12 months if no target date

        # Parse target date
        try:
            target_dt = datetime.fromisoformat(target_date_str[:10])
        except (ValueError, TypeError):
            target_dt = datetime.utcnow() + timedelta(days=365)

        days_until_deadline = max(0, (target_dt - datetime.utcnow()).days)
        monthly_needed = remaining / max(1, days_until_deadline / 30.44)

        # ETA
        if monthly_savings > 0:
            eta_months = remaining / monthly_savings
            eta_days = int(eta_months * 30.44)
        else:
            eta_days = 99999

        projected_date = (datetime.utcnow() + timedelta(days=eta_days)).date()
        on_track = eta_days <= days_until_deadline if days_until_deadline > 0 else False
        shortfall_risk = eta_days > days_until_deadline * 1.15 if days_until_deadline > 0 else True

        return {
            "eta_days": eta_days,
            "on_track": on_track,
            "projected_completion_date": projected_date.isoformat(),
            "monthly_savings_needed": round(monthly_needed, 2),
            "current_monthly_savings": round(monthly_savings, 2),
            "shortfall_risk": shortfall_risk,
            "confidence": 0.75,
            "processing_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Model health ──────────────────────────────────────────────────────────
@router.get(
    "/health",
    summary="Check load status of all 4 ML models",
)
async def model_health(
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    return pl.get_model_health()