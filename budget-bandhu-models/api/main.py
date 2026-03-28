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


import os
import threading
try:
    from pyngrok import ngrok
    from dotenv import load_dotenv
    # Load ML's own .env first (if present), then fall back to RAG .env for shared secrets
    ml_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    rag_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "budget-bandhu-rag", ".env")
    load_dotenv(rag_env)   # load shared secrets (both ngrok tokens)
    load_dotenv(ml_env, override=True)   # ML-specific overrides win
except ImportError:
    pass

ML_STATIC_DOMAIN = "unoperated-merideth-sparklike.ngrok-free.dev"

def start_ngrok():
    try:
        from pyngrok import conf as pyngrok_conf
        token = os.getenv("ARYAN_LOMTE_SOMAIYA_EDU_AUTHTOKEN")
        if not token:
            log.warning("[NGROK] ARYAN_LOMTE_SOMAIYA_EDU_AUTHTOKEN not set — skipping tunnel")
            return
        # Use a dedicated config so this agent never shares a session with the RAG backend
        ml_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(ml_root, "ngrok_ml.yml")
        pyngrok_config = pyngrok_conf.PyngrokConfig(
            config_path=config_path,
            auth_token=token,
        )
        tunnel = ngrok.connect(
            addr=8001,
            domain=ML_STATIC_DOMAIN,
            pyngrok_config=pyngrok_config,
        )
        url = tunnel.public_url
        log.info(f"[NGROK] ML tunnel active: {url}")
        with open("ngrok_url.txt", "w") as f:
            f.write(f"Public URL: {url}\n")
    except Exception as e:
        log.error(f"[NGROK] Failed to start ML tunnel: {e}")

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
    
    threading.Thread(target=start_ngrok, daemon=True).start()
    
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
            "POST /ml/analyze",
            "POST /ml/categorize",
            "POST /ml/anomalies",
            "POST /ml/forecast",
            "POST /ml/budget/optimize",
            "GET  /ml/health",
        ]
    }