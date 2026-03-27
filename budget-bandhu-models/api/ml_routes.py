from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from api.schemas import (
    CategorizeRequest, AnomalyRequest, ForecastRequest, UserFinancialState
)
from intelligence.policy_learner import UserFinancialState as PolicyState
from intelligence.ml_pipeline import BudgetBandhuMLPipeline
import time

router   = APIRouter(prefix="/api/ml", tags=["ML Models"])
pipeline = BudgetBandhuMLPipeline()


def get_pipeline() -> BudgetBandhuMLPipeline:
    return pipeline


# ── Full CSV pipeline ─────────────────────────────────────────────────────
@router.post(
    "/process-csv",
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
        t0      = time.time()
        results = pl.categorizer.categorize_batch(req.descriptions)
        elapsed = round((time.time() - t0) * 1000, 1)
        return {
            "results":        [r.dict() for r in results],
            "count":          len(results),
            "processing_ms":  elapsed,
            "model_active":   pl.categorizer.is_loaded(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Anomaly detection ─────────────────────────────────────────────────────
@router.post(
    "/anomaly/detect",
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


# ── Model health ──────────────────────────────────────────────────────────
@router.get(
    "/health",
    summary="Check load status of all 4 ML models",
)
async def model_health(
    pl: BudgetBandhuMLPipeline = Depends(get_pipeline),
):
    return pl.get_model_health()