import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.ml_routes import router, pipeline

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log        = logging.getLogger("budgetbandhu")
START_TIME = time.time()


# ── Lifespan — warm up all models on startup ──────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("BudgetBandhu ML Microservice starting up...")
    health = pipeline.get_model_health()
    for model_name, status in health.items():
        if model_name not in ("all_healthy", "models_active"):
            icon = "✅" if status else "⚠ "
            log.info(f"  {icon}  {model_name}: {'loaded' if status else 'fallback mode'}")
    log.info(f"  All healthy: {health['all_healthy']}")
    log.info(f"  Active    : {health.get('models_active', [])}")
    log.info("=" * 60)
    yield
    log.info("ML Microservice shutting down.")


# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "BudgetBandhu ML Microservice",
    description = (
        "4-model ML pipeline powering BudgetBandhu — AI personal finance assistant "
        "for Indian students and first-time earners.\n\n"
        "**Models:**\n"
        "- `all-MiniLM-L6-v2 + LogisticRegression` — UPI transaction categorisation\n"
        "- `IsolationForest` — Spending anomaly detection\n"
        "- `BiLSTM (PyTorch)` — 7-day spending forecast\n"
        "- `Q-Learning` — Adaptive budget optimisation"
    ),
    version     = "1.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Request timing middleware ─────────────────────────────────────────────
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0       = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = str(
        round((time.time() - t0) * 1000, 1)
    )
    return response


# ── Global exception handler ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code = 500,
        content     = {"detail": "Internal server error.", "error": str(exc)},
    )


# ── Routes ────────────────────────────────────────────────────────────────
app.include_router(router)


@app.get("/health", tags=["System"])
async def health():
    model_health = pipeline.get_model_health()
    return {
        "status":         "ok" if model_health["all_healthy"] else "degraded",
        "uptime_seconds": int(time.time() - START_TIME),
        "models":         model_health,
        "version":        "1.0.0",
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "service":  "BudgetBandhu ML Microservice",
        "version":  "1.0.0",
        "docs":     "/docs",
        "health":   "/health",
        "endpoints": [
            "POST /api/ml/process-csv",
            "POST /api/ml/categorize",
            "POST /api/ml/anomaly/detect",
            "POST /api/ml/forecast",
            "POST /api/ml/budget/optimize",
            "GET  /api/ml/health",
        ]
    }