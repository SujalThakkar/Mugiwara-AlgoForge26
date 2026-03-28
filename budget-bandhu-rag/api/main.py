import dotenv
import os
dotenv.load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("BudgetBandhu")

import threading
try:
    from pyngrok import ngrok
except ImportError:
    pass

RAG_STATIC_DOMAIN = "babylike-overtimorously-stacey.ngrok-free.dev"

def start_ngrok():
    try:
        from pyngrok import conf as pyngrok_conf
        token = os.getenv("LORDAKJ05_GMAIL_COM_AUTHTOKEN")
        if not token:
            logger.warning("[NGROK] LORDAKJ05_GMAIL_COM_AUTHTOKEN not set — skipping tunnel")
            return
        rag_root = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(rag_root, "ngrok_rag.yml")
        pyngrok_config = pyngrok_conf.PyngrokConfig(
            config_path=config_path,
            auth_token=token,
        )
        tunnel = ngrok.connect(
            addr=8000,
            domain=RAG_STATIC_DOMAIN,
            pyngrok_config=pyngrok_config,
        )
        url = tunnel.public_url
        logger.info(f"[NGROK] RAG tunnel active: {url}")
    except Exception as e:
        logger.error(f"[NGROK] Failed to start RAG tunnel: {e}")

app = FastAPI(title="BudgetBandhu API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True
)

# ── Route registrations ──────────────────────────────────────
from api.routes.chat         import router as chat_router
from api.routes.transactions import router as transactions_router
from api.routes.dashboard    import router as dashboard_router
from api.routes.goals        import router as goals_router
from api.routes.budget       import router as budget_router
from api.routes.insights     import router as insights_router
from api.routes.literacy     import router as literacy_router
# Web3 / Goals 2.0 routers
from api.routes.escrow       import router as escrow_router
from api.routes.savings      import router as savings_router

app.include_router(chat_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(goals_router)
app.include_router(budget_router)
app.include_router(insights_router)
app.include_router(literacy_router)
app.include_router(escrow_router)
app.include_router(savings_router)


# ── Health ───────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "mode": "unified_mobile_core"}


@app.get("/api/v1/health/db")
async def health_db():
    try:
        from database.mongo_manager import MongoManager
        db = MongoManager()
        await db.connect()
        colls = await db.db.list_collection_names()
        await db.close()
        return {"mongodb": "connected", "collections": colls}
    except Exception as e:
        return {"mongodb": "error", "detail": str(e)}


# ── Startup: pre-warm AgentController ───────────────────────
@app.on_event("startup")
async def startup():
    logger.info("[MAIN] Starting up...")
    # Connect to MongoDB (needed by get_database() dependency in all routes)
    from api.database import Database
    await Database.connect()
    # Start ngrok in background
    threading.Thread(target=start_ngrok, daemon=True).start()
    # Pre-warm AgentController
    try:
        from api.routes.chat import get_controller
        get_controller()
    except Exception as e:
        logger.warning(f"[MAIN] AgentController pre-warm failed (non-fatal): {e}")
    logger.info("[MAIN] ✅ Ready")

