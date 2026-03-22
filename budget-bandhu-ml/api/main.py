"""
BudgetBandhu Unified ML API
Mobile-First + Agent + ML Integration
Full Feature Set (Ditto app.py features)

Author: Aryan & Tanuj
version: 4.2 (Unified + Core Integration)
"""
import dotenv
import os
import sys

# Load environment variables FIRST
dotenv.load_dotenv(override=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import json
import logging
import traceback
import threading


# Add parent directory to path to allow running as script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows encoding issue for emojis
if sys.platform == 'win32':
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    # Backup for older Python versions
    elif isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

# Modules
from api.database import Database
from api.routes import user, transactions, chat, forecast, insights, ocr, dashboard, budget, goals, gamification, whatsapp, telegram
from intelligence.phi3_rag import Phi3RAG

# Core Components
from core.agent_controller import AgentController
from memory.memory_manager import MemoryManager
from memory.conversation_manager import ConversationManager
from database.mongo_manager import MongoManager

# Ngrok support
try:
    from pyngrok import ngrok
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False

ENABLE_NGROK = os.getenv("ENABLE_NGROK", "True").lower() == "true"
NGROK_PORT = 8000

# Logging Setup
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    handlers=[
        logging.FileHandler(f"logs/api_{int(time.time())}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("BudgetBandhu")

class RequestLogger:
    @staticmethod
    def log_request(endpoint: str, method: str, body: dict):
        logger.info(f"[REQ] | {method} {endpoint}")

    @staticmethod
    def log_error(endpoint: str, error: Exception):
        logger.error(f"[ERR] | {endpoint} | {str(error)}")

def start_ngrok():
    if not ENABLE_NGROK or not NGROK_AVAILABLE: return
    try:
        ngrok.kill()
        url = ngrok.connect(NGROK_PORT).public_url
        logger.info(f"[NGROK] Public URL: {url}")
        with open("ngrok_url.txt", "w") as f:
            f.write(f"Public URL: {url}\n")
    except Exception as e:
        logger.error(f"Ngrok failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("[START] Starting BudgetBandhu Unified API...")
    await Database.connect()
    
    # Initialize Core Agent Components
    try:
        logger.info("[INIT] Initializing Agent Core...")
        
        # 1. Mongo Bridge (Reuse connection)
        # We manually bridge api.database.client to MongoManager 
        # so core components use the same connection
        mongo_mgr = MongoManager(os.getenv("MONGO_URL", ""), os.getenv("DATABASE_NAME", "budget_bandhu"))
        mongo_mgr.client = Database.client
        mongo_mgr.db = Database.get_db()
        
        # Manually initialize collections because we skipped .connect()
        mongo_mgr.users = mongo_mgr.db.users
        mongo_mgr.memories = mongo_mgr.db.memories
        mongo_mgr.conversations = mongo_mgr.db.conversations
        mongo_mgr.messages = mongo_mgr.db.messages
        mongo_mgr.transactions = mongo_mgr.db.transactions
        
        logger.info("[INIT] Mongo Manager Bridged & Collections Init")
        
        # 2. Managers
        mem_mgr = MemoryManager(mongo_mgr)
        conv_mgr = ConversationManager(mongo_mgr)
        
        # 3. Intelligence
        phi3 = Phi3RAG(base_model="budget-bandhu")
        
        # 4. ML Models (Transactions)
        from intelligence.categorizer import TransactionCategorizer
        from intelligence.anomaly_detector import AnomalyDetector
        from intelligence.user_anomaly_detector import UserAnomalyDetector
        
        logger.info("[INIT] Loading Transaction ML Models...")
        cat = TransactionCategorizer(phi3_model_path="models/phi3_categorizer")
        
        ad = None
        try:
            ad = AnomalyDetector(
                model_path="models/isolation_forest/model.pkl",
                category_map_path="models/isolation_forest/category_map.json"
            )
        except Exception as e:
            logger.error(f"[INIT] [ERR] Anomaly Detector Load Failed: {e}")
            
        uad = None
        try:
            uad = UserAnomalyDetector(
                models_dir="models/user_anomaly",
                category_map_path="models/isolation_forest/category_map.json"
            )
        except Exception as e:
            logger.error(f"[INIT] [ERR] User Anomaly Detector Load Failed: {e}")
            
        transactions.set_ml_models(cat, ad, uad)
        
        # 5. Controller
        agent_ctrl = AgentController(
            phi3_rag=phi3,
            memory_manager=mem_mgr,
            conversation_manager=conv_mgr,
            categorizer=cat
        )
        
        chat.set_agent_controller(agent_ctrl)
        whatsapp.set_agent_controller(agent_ctrl)
        telegram.set_agent_controller(agent_ctrl)
        logger.info("[INIT] [OK] Agent Controller & ML Ready")
    except Exception as e:
        logger.error(f"[INIT] [ERR] Agent Init Failed: {e}")
        logger.error(traceback.format_exc())
    
    # Start Ngrok Thread
    if ENABLE_NGROK:
        threading.Thread(target=start_ngrok, daemon=True).start()

    yield
    
    # Shutdown
    await Database.disconnect()
    logger.info("[STOP] API Shutdown")

app = FastAPI(
    title="BudgetBandhu Unified API",
    version="4.2",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"[OUT] {request.method} {request.url.path} | {response.status_code} | {duration:.3f}s")
    return response

# Routes
app.include_router(user.router)
app.include_router(transactions.router)
app.include_router(chat.router)
app.include_router(forecast.router)
app.include_router(insights.router)
app.include_router(ocr.router)
app.include_router(dashboard.router)
app.include_router(budget.router)
app.include_router(goals.router)
app.include_router(gamification.router)
app.include_router(whatsapp.router)
app.include_router(telegram.router)

@app.get("/")
def root():
    return {"message": "BudgetBandhu Unified API v4.2", "status": "active"}

@app.get("/health")
def health():
    return {"status": "healthy", "mode": "unified_mobile_core"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
