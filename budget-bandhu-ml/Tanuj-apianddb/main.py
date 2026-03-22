"""
FastAPI Main Application - BudgetBandhu ML API v3.0
MongoDB + All ML Models Integrated

Author: Tanuj
Date: Jan 16, 2026
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Database
from api.database import Database

# Route imports - All MongoDB + ML powered routes
from api.routes.user import router as user_router
from api.routes.transactions import router as transactions_router
from api.routes.dashboard import router as dashboard_router
from api.routes.budget import router as budget_router
from api.routes.goals import router as goals_router
from api.routes.gamification import router as gamification_router
from api.routes.insights import router as insights_router
from api.routes.forecast import router as forecast_router

# Agent integration (Aryan - optional)
AGENT_AVAILABLE = False
try:
    from core.agent_controller import AgentController
    from core.memory_system import MemorySystem
    from intelligence.phi3_rag import Phi3RAG
    from api.routes.chat import router as chat_router, set_agent_controller
    AGENT_AVAILABLE = True
except ImportError as e:
    print(f"[MAIN] Agent not available (expected): {e}")


# ===== LIFESPAN EVENTS =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: Connect to MongoDB
    print("[MAIN] ═══════════════════════════════════════════════════")
    print("[MAIN] Starting BudgetBandhu ML API v3.0")
    print("[MAIN] ═══════════════════════════════════════════════════")
    
    await Database.connect()
    print("[MAIN] MongoDB connected [OK]")
    
    # Initialize agent if available
    if AGENT_AVAILABLE:
        try:
            memory_system = MemorySystem()
            phi3_rag = Phi3RAG(model_path="models/phi3_chatbot")
            agent_controller = AgentController(
                memory_system=memory_system,
                phi3_rag=phi3_rag
            )
            set_agent_controller(agent_controller)
            app.include_router(chat_router)
            print("[MAIN] Agent controller integrated [OK]")
        except Exception as e:
            print(f"[MAIN] Agent load failed: {e}")
    
    print("[MAIN] ═══════════════════════════════════════════════════")
    print("[MAIN] API Ready! http://localhost:8000/docs")
    print("[MAIN] ═══════════════════════════════════════════════════")
    
    yield
    
    # Shutdown: Disconnect MongoDB
    await Database.disconnect()
    print("[MAIN] MongoDB disconnected")


# ===== CREATE APP =====
app = FastAPI(
    title="Quant.ai - BudgetBandhu ML API",
    description="ML-Powered Personal Finance API with MongoDB",
    version="3.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== INCLUDE ROUTERS =====
app.include_router(user_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(budget_router)
app.include_router(goals_router)
app.include_router(gamification_router)
app.include_router(insights_router)
app.include_router(forecast_router)


# ===== ROOT & HEALTH =====
@app.get("/")
async def root():
    """API Root"""
    return {
        "name": "BudgetBandhu ML API",
        "version": "3.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    db_connected = Database.client is not None
    
    return {
        "status": "healthy" if db_connected else "degraded",
        "version": "3.0",
        "database": "connected" if db_connected else "disconnected",
        "agent_available": AGENT_AVAILABLE,
        "ml_components": {
            "categorizer": "ready",
            "anomaly_detector": "ready",
            "lstm_forecaster": "ready",
            "policy_learner": "ready"
        },
        "endpoints": {
            "user": "/api/v1/user",
            "transactions": "/api/v1/transactions",
            "dashboard": "/api/v1/dashboard",
            "budget": "/api/v1/budget",
            "goals": "/api/v1/goals",
            "gamification": "/api/v1/gamification",
            "insights": "/api/v1/insights"
        }
    }


# ===== API DOCS SUMMARY =====
"""
┌─────────────────────────────────────────────────────────────────────────┐
│                       BudgetBandhu API v3.0 Endpoints                    │
├─────────────────────────────────────────────────────────────────────────┤
│ USER ROUTES (/api/v1/user)                                              │
│   POST /register         - Create user + auto budget + gamification     │
│   POST /login            - Login user                                   │
│   GET  /{user_id}        - Get user profile                             │
│   PUT  /{user_id}/income - Update income                                │
├─────────────────────────────────────────────────────────────────────────┤
│ TRANSACTIONS (/api/v1/transactions)                                      │
│   POST /                 - Add single transaction (ML processed)        │
│   POST /bulk             - Bulk upload (ML processed)                   │
│   POST /upload-csv       - CSV upload (ML processed)                    │
│   GET  /{user_id}        - Get transactions                             │
│   GET  /{user_id}/stats  - Get transaction stats                        │
│   GET  /{user_id}/anomalies - Get flagged anomalies                     │
├─────────────────────────────────────────────────────────────────────────┤
│ DASHBOARD (/api/v1/dashboard)                                            │
│   GET  /{user_id}        - Full dashboard with ML insights              │
│   GET  /{user_id}/spending-trend - Daily spending trend                 │
├─────────────────────────────────────────────────────────────────────────┤
│ BUDGET (/api/v1/budget)                                                  │
│   GET  /{user_id}        - Get budget allocations                       │
│   PUT  /{user_id}        - Update budget (manual)                       │
│   GET  /{user_id}/recommend - Get ML recommendations (PolicyLearner)    │
│   POST /{user_id}/feedback  - Submit recommendation feedback            │
│   POST /{user_id}/reset     - Reset to default 50/30/20                 │
├─────────────────────────────────────────────────────────────────────────┤
│ GOALS (/api/v1/goals)                                                    │
│   GET  /{user_id}        - Get all goals with ETA                       │
│   POST /                 - Create new goal                              │
│   PUT  /{goal_id}/contribute - Add money to goal                        │
│   GET  /{goal_id}/eta    - Get LSTM ETA prediction                      │
│   DELETE /{goal_id}      - Delete goal                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ GAMIFICATION (/api/v1/gamification)                                      │
│   GET  /{user_id}        - Get XP, level, badges                        │
│   POST /{user_id}/xp     - Add XP                                       │
│   POST /{user_id}/check-badges - Check ML-triggered badges              │
│   GET  /leaderboard/{user_id}  - Get leaderboard                        │
└─────────────────────────────────────────────────────────────────────────┘
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
