"""
Budget Bandhu - Unified ML Microservice (Async + MongoDB)
Main FastAPI application with RAG Chat + Analytics

Integrates:
- RAG chatbot (Phi-3.5)
- MongoDB Storage (Async Motor)
- Categorization, forecasting, anomaly detection
- Analytics & insights
- Public exposure via ngrok (pyngrok)

Author: Aryan Lomte (Integration), Tanuj (Analytics Models)
Version: 2.1.0 (Mongo Edition)
"""

import os
import sys
import time
import json
import uvicorn
import logging
import threading
import traceback
from datetime import datetime
from typing import Optional, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# PYNGROK (WITH FALLBACK)
# ============================================================
try:
    from pyngrok import ngrok
    NGROK_AVAILABLE = True
except ImportError:
    NGROK_AVAILABLE = False

# ============================================================
# INTERNAL MODULES
# ============================================================
from database.mongo_manager import MongoManager
from memory.memory_manager import MemoryManager
from memory.conversation_manager import ConversationManager
from intelligence.phi3_rag import Phi3RAG
from agents.agent_controller import AgentController
from intelligence.tanuj_integration import get_tanuj_service

# ============================================================
# GLOBAL CONFIGURATION
# ============================================================
SERVICE_NAME = "BudgetBandhu"
SERVICE_VERSION = "2.1.0"
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = "budget_bandhu"

NGROK_AUTH_TOKEN = "36Qd2x8NtZbbKwgdvo06BTJqAsH_4kEZx28UL7XfDDXpjczwA"
NGROK_PORT = 8000
ENABLE_NGROK = True

# ============================================================
# LOGGING SETUP
# ============================================================
os.makedirs("logs", exist_ok=True)

class SafeFormatter(logging.Formatter):
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            record.msg = str(record.msg).encode('ascii', 'ignore').decode('ascii')
            return super().format(record)

file_handler = logging.FileHandler(
    f"logs/app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(SafeFormatter('%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s', '%Y-%m-%d %H:%M:%S'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(SafeFormatter('%(asctime)s | %(levelname)-8s | %(message)s', '%H:%M:%S'))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.DEBUG)

class RequestLogger:
    @staticmethod
    def log_request(endpoint: str, method: str, user_id: Optional[str], body: Dict):
        logger.info(f"🔵 REQUEST  | {method:4s} {endpoint:30s} | user_id={user_id}")
        logger.debug(f"   Request Body: {json.dumps(body, indent=2, default=str)[:500]}")

    @staticmethod
    def log_response(endpoint: str, status: str, duration: float, size: int):
        logger.info(f"🟢 RESPONSE | {endpoint:30s} | {status:7s} | {duration:.3f}s | {size}B")

    @staticmethod
    def log_error(endpoint: str, error: Exception):
        logger.error(f"🔴 ERROR    | {endpoint:30s} | {str(error)}")
        logger.debug(traceback.format_exc())

# ============================================================
# NGROK STARTUP
# ============================================================
def start_ngrok():
    if not ENABLE_NGROK: return
    if not NGROK_AVAILABLE:
        logger.warning("[NGROK] pyngrok not installed")
        return
    try:
        logger.info("[NGROK] Starting tunnel...")
        ngrok.set_auth_token(NGROK_AUTH_TOKEN)
        ngrok.kill()
        time.sleep(1)
        tunnel = ngrok.connect(NGROK_PORT, bind_tls=True)
        public_url = tunnel.public_url
        logger.info("=" * 70)
        logger.info(f"[NGROK] ✅ SUCCESS! URL: {public_url}")
        logger.info("=" * 70)
        with open("ngrok_url.txt", "w") as f:
            f.write(f"Public URL: {public_url}\n")
    except Exception as e:
        logger.error(f"[NGROK] Failed: {e}")

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="Budget Bandhu ML API (Mongo)", version=SERVICE_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_timing(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"📤 {request.method} {request.url.path} | {response.status_code} | {duration:.3f}s")
    return response

# ============================================================
# COMPONENT INITIALIZATION
# ============================================================
logger.info("🚀 INITIALIZING COMPONENTS (MONGODB MODE)...")

# Managers (Global)
mongo_manager = MongoManager(MONGODB_URL, DB_NAME)
memory_manager = MemoryManager(mongo_manager)
conversation_manager = ConversationManager(mongo_manager)
phi3 = Phi3RAG(base_model="budget-bandhu")

# Agent
agent = AgentController(phi3, memory_manager, conversation_manager)

# ML Models
tanuj_ml = get_tanuj_service()

@app.on_event("startup")
async def startup_db():
    logger.info("📡 Connecting to MongoDB...")
    await mongo_manager.connect()
    logger.info("✅ MongoDB Connected")

@app.on_event("shutdown")
async def shutdown_db():
    await mongo_manager.close()
    logger.info("❌ MongoDB Closed")

# ============================================================
# PYDANTIC MODELS (Updated for Mobile Number ID)
# ============================================================
class ChatRequest(BaseModel):
    user_id: str  # Mobile Number
    query: str
    session_id: Optional[str] = None

class MemorySemanticRequest(BaseModel):
    user_id: str
    attribute_type: str
    value: str

class MemoryEpisodicRequest(BaseModel):
    user_id: str
    event_summary: str
    trigger_type: str
    metadata: Optional[Dict] = None

class CategorizeRequest(BaseModel):
    description: str
    amount: float

class ForecastRequest(BaseModel):
    user_id: str
    months: int = 3

class AnomalyCheckRequest(BaseModel):
    description: str
    amount: float
    category: Optional[str] = None

class TransactionRequest(BaseModel):
    user_id: str
    description: str
    amount: float
    category: Optional[str] = None

# ============================================================
# ENDPOINTS
# ============================================================

@app.post("/chat", tags=["Chat"])
async def chat(request: ChatRequest):
    """AI chat using MongoDB-backed memory"""
    start = time.time()
    RequestLogger.log_request("/chat", "POST", request.user_id, request.dict())
    try:
        result = await agent.execute_turn(
            user_id=request.user_id,
            query=request.query,
            session_id=request.session_id
        )
        duration = time.time() - start
        RequestLogger.log_response("/chat", "success", duration, len(str(result)))
        return {"success": True, **result}
    except Exception as e:
        RequestLogger.log_error("/chat", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memory/{user_id}", tags=["Memory"])
async def get_memory(user_id: str):
    """Get memories for mobile number"""
    try:
        memories = await memory_manager.get_user_memories(user_id)
        return {"success": True, "user_id": user_id, **memories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memory/semantic", tags=["Memory"])
async def store_semantic(request: MemorySemanticRequest):
    try:
        mid = await memory_manager.store_semantic_memory(
            request.user_id, request.attribute_type, request.value
        )
        return {"success": True, "memory_id": mid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/memory/episodic", tags=["Memory"])
async def store_episodic(request: MemoryEpisodicRequest):
    try:
        mid = await memory_manager.store_episodic_memory(
            request.user_id, request.event_summary, request.trigger_type, request.metadata
        )
        return {"success": True, "memory_id": mid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/categorize", tags=["Analytics"])
async def categorize(request: CategorizeRequest):
    try:
        result = tanuj_ml.categorize_expense(request.description, request.amount)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/forecast", tags=["Analytics"])
async def forecast(request: ForecastRequest):
    """Forecast using historical data from MongoDB"""
    try:
        # Fetch history from Mongo
        cursor = mongo_manager.memories.find(
            {"user_id": request.user_id, "type": "episodic", "trigger_type": "expense"}
        ).sort("timestamp", -1).limit(100)
        
        history = []
        async for doc in cursor:
            # Adapt Mongo doc to simple dict for Tanuj
            meta = doc.get("meta_data", {})
            history.append({
                "amount": meta.get("amount", 0),
                "date": doc["timestamp"]
            })
            
        result = tanuj_ml.forecast_expenses(request.user_id, history, request.months)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/anomaly-check", tags=["Analytics"])
async def anomaly_check(request: AnomalyCheckRequest):
    try:
        result = tanuj_ml.detect_anomaly(request.dict())
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transaction/add", tags=["Analytics"])
async def add_transaction(request: TransactionRequest):
    """Add transaction -> Categorize -> Anomaly -> Store (Mongo)"""
    start = time.time()
    try:
        # 1. Categorize
        if not request.category:
            cat_result = tanuj_ml.categorize_expense(request.description, request.amount)
            category = cat_result["category"]
        else:
            category = request.category
            
        # 2. Anomaly
        anomaly = tanuj_ml.detect_anomaly({
            "description": request.description,
            "amount": request.amount,
            "category": category
        })
        
        # 3. Store in Mongo
        mid = await memory_manager.store_episodic_memory(
            request.user_id,
            f"Spent ₹{request.amount} on {request.description}",
            "expense",
            {
                "description": request.description,
                "amount": request.amount,
                "category": category,
                "is_anomaly": anomaly["is_anomaly"],
                "anomaly_score": anomaly.get("anomaly_score", 0)
            }
        )
        
        return {
            "success": True,
            "memory_id": mid,
            "category": category,
            "is_anomaly": anomaly["is_anomaly"],
            "warning": anomaly.get("reason") if anomaly["is_anomaly"] else None
        }
    except Exception as e:
        RequestLogger.log_error("/transaction/add", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/{user_id}", tags=["Analytics"])
async def analytics(user_id: str):
    """Get analytics using Mongo Data"""
    try:
        cursor = mongo_manager.memories.find(
            {"user_id": user_id, "type": "episodic", "trigger_type": "expense"}
        ).limit(200)
        
        txns = []
        async for doc in cursor:
            meta = doc.get("meta_data", {})
            txns.append({
                "amount": meta.get("amount", 0),
                "category": meta.get("category", "Other"),
                "description": doc.get("event_summary")
            })
            
        result = tanuj_ml.generate_insights(user_id, txns)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "mode": "mongodb", "version": SERVICE_VERSION}

if __name__ == "__main__":
    logger.info("📡 Starting Mongo-backed API...")
    if ENABLE_NGROK:
        threading.Thread(target=start_ngrok, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=NGROK_PORT)
