# BudgetBandhu — Session Handoff Context
**Date:** 2026-03-28 | **Thread to continue from**

---

## 🏗️ Project Structure

```
e:\PICT Techfiesta\BudgetBandhu\
├── budget-bandhu-rag\         ← RAG Gateway + AgentController (port 8000)
├── budget-bandhu-models\      ← ML Microservice (port 8001)
└── budget-bandhu-frontend\    ← Next.js frontend (npm run dev → port 3000)
```

---

## ✅ What Was Fixed This Session

### Frontend (`budget-bandhu-frontend`)
- **Build now passes** — `npm run build` exits with code 0, all 23 pages prerender successfully
- **Removed ALL mock-data dependencies** from the live render path:
  - `SpendingSparkline.tsx` — empty array guard
  - `CashflowLineChart.tsx` — empty data early return
  - `SpendingDonutChart.tsx` — empty categoryBreakdown guard + removed `mockData` import
  - `BudgetProgressBars.tsx` — empty allocations guard + removed `mockData` import
  - `EmergencyFundBarometer.tsx` — fully removed `mockData` dependency, prop-only now, uses `goal.monthly_expenses || 30000` as safe default
  - `FinancialTimeMachine.tsx` — removed `mockData.financialHistory` spread, now shows empty state if no data
  - `TaxOptimizerDashboard.tsx` — guarded `mockData.tax` access with `?.` optional chaining
- **`mock-data.ts`** is now a skeleton with typed empty arrays (exists at `src/lib/api/mock-data.ts`, 677 bytes)

### RAG Backend (`budget-bandhu-rag/api/main.py`)
- **Added ngrok auto-start** in `startup()` via `threading.Thread(target=start_ngrok, daemon=True).start()`
- **Uses `LORDAKJ05_GMAIL_COM_AUTHTOKEN`** (gmail account) to avoid conflict with ML backend which uses `ARYAN_LOMTE_SOMAIYA_EDU_AUTHTOKEN` (somaiya account)
- **ngrok URL written to `ngrok_url.txt`** in the RAG root dir after successful tunnel open

### RAG Backend (`budget-bandhu-rag/core/agent_controller.py`)
- **Fixed `GatingSystem.check()` AttributeError** — replaced direct `.check(q)` call with `getattr()` fallback chain: `check → evaluate → validate → is_safe`, wrapped in non-blocking `try/except` so gating failure never crashes a chat turn
- **Fixed `ConversationManager(self.db)` → `ConversationManager(_atlas)`** — was passing MongoManager wrapper instead of Motor async DB handle

---

## ⚠️ Ngrok Situation — IMPORTANT

**Free tier = 3 simultaneous agent sessions max.**

| Service | Port | Token Used | Expected Tunnel URL |
|---|---|---|---|
| ML Microservice | 8001 | `ARYAN_LOMTE_SOMAIYA_EDU_AUTHTOKEN` | `https://unoperated-merideth-sparklike.ngrok-free.dev` |
| RAG Gateway | 8000 | `LORDAKJ05_GMAIL_COM_AUTHTOKEN` | `https://babylike-overtimorously-stacey.ngrok-free.dev` |

**If you hit `ERR_NGROK_108` (session limit):**
```powershell
taskkill /F /IM ngrok.exe
# Wait 5 seconds, then restart both backends
```

**Do NOT use `--reload` flag** on final hackathon demo — reload spawns extra watcher processes that eat ngrok sessions:
```powershell
# RAG (no --reload for demo)
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000

# ML
python -m uvicorn api.main:app --port 8001
```

---

## 🔧 Startup Order (ALWAYS follow this order)

1. **Start Ollama** (must be running for RAG): `ollama serve` (or it's already running as a service)
2. **Start ML backend** → `cd budget-bandhu-models` → `venv\Scripts\activate` → `python -m uvicorn api.main:app --port 8001`
3. **Wait for ML ngrok URL** to appear: `[NGROK] Public URL: https://unoperated-merideth-sparklike.ngrok-free.dev`
4. **Start RAG backend** → `cd budget-bandhu-rag` → `venv\Scripts\activate` → `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000`
5. **Wait for RAG ready** log: `[MAIN] ✅ Ready`
6. **Start frontend** → `cd budget-bandhu-frontend` → `npm run dev`

---

## 🗺️ Architecture Summary

```
Next.js Frontend (port 3000)
      │  NEXT_PUBLIC_API_URL = https://babylike-overtimorously-stacey.ngrok-free.dev
      ▼
RAG Backend Gateway (budget-bandhu-rag, port 8000)
      ├── AgentController → MongoDB Atlas (all memory tiers)
      ├── Phi3RAG → Ollama (budget-bandhu model + nomic-embed-text)
      └── MLClient → https://unoperated-merideth-sparklike.ngrok-free.dev
                            │
                            ▼
                   ML Backend (budget-bandhu-models, port 8001)
                      ├── Categorizer (LogisticRegression)
                      ├── AnomalyDetector (IsolationForest)
                      ├── Forecaster (BiLSTM, CUDA)
                      └── PolicyLearner (Q-table)
```

---

## 📁 Key Files Reference

### RAG Backend
| File | Purpose |
|---|---|
| `api/main.py` | FastAPI app, route registration, ngrok startup |
| `core/agent_controller.py` | **CANONICAL** — main chat logic, all memory wiring |
| `core/gating.py` | Topic gating — check what method name is actually defined here |
| `intelligence/phi3_rag.py` | Ollama Phi-3.5 + nomic embeddings |
| `intelligence/ml_client.py` | HTTP client forwarding to ML backend |
| `database/mongo_manager.py` | MongoManager wrapper — `.get_motor_db()` returns Motor async handle |
| `memory/conversation_manager.py` | Expects Motor async DB handle (not MongoManager wrapper) |
| `api/routes/chat.py` | POST /api/v1/chat route |
| `.env` | All secrets — MongoDB, ngrok tokens, ML URL |

### ML Backend
| File | Purpose |
|---|---|
| `api/main.py` | FastAPI app + ngrok startup (uses somaiya token) |
| `api/ml_routes.py` | All /ml/* routes |
| `models/pipeline.py` | Loads all 4 ML models on startup |

### Frontend
| File | Purpose |
|---|---|
| `.env.local` | `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_ML_API_URL` |
| `src/lib/api/ml-api.ts` | All API hooks (`useMLApi`, `useDashboard`, etc.) — live only, no mock mode |
| `src/lib/api/client.ts` | Base `callApi()` wrapper |
| `src/lib/api/mock-data.ts` | Skeleton with typed empty arrays — exists to satisfy imports |

---

## 🐛 Known Remaining Issues / Watch Out For

1. **`core/gating.py` method name** — The gating fix in `agent_controller.py` uses `getattr()` fallback so it won't crash, but check what the actual method is named (`def evaluate`, `def validate`, `def is_safe`, etc.) via:
   ```powershell
   findstr "def " core\gating.py
   ```

2. **`--reload` flag and ngrok** — Using `--reload` during dev spawns multiple processes, consuming extra ngrok sessions. For demo day, drop `--reload`.

3. **Multiple stale RAG uvicorn processes** — There were 4+ RAG uvicorn processes running simultaneously during this session (visible in metadata). Kill stale ones before restarting:
   ```powershell
   taskkill /F /IM python.exe  # nuclear option — kills all python
   # OR use Task Manager to find and kill specific uvicorn PIDs
   ```

4. **`.env.local` tunnel URLs may be stale** — After each ngrok restart, the tunnel URLs stay the same (static domains from paid/reserve), so this shouldn't be an issue if using the reserved domains listed above.

---

## 💬 API Endpoints (Quick Reference)

### RAG Gateway (port 8000)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/chat` | Main AI chat endpoint |
| POST | `/api/v1/transactions` | Add transaction |
| GET | `/api/v1/transactions/{user_id}` | Get transactions |
| GET | `/api/v1/dashboard/{user_id}` | Dashboard summary |
| GET | `/api/v1/insights/{user_id}` | Spending insights |
| GET | `/api/v1/goals/{user_id}` | Financial goals |
| GET | `/api/v1/budget/{user_id}` | Budget allocations |
| GET | `/health` | Health check |
| Swagger | `/docs` | Interactive API docs |

### ML Backend (port 8001)
| Method | Path | Purpose |
|---|---|---|
| POST | `/ml/analyze` | Full ML pipeline (all 4 models) |
| POST | `/ml/categorize` | Transaction categorization |
| POST | `/ml/anomalies` | Anomaly detection |
| POST | `/ml/forecast` | 7-day BiLSTM forecast |
| POST | `/ml/budget/optimize` | Q-learning budget optimization |
| GET | `/health` | Health check |

---

## 🧪 Quick Smoke Test

```bash
# Test RAG health
curl https://babylike-overtimorously-stacey.ngrok-free.dev/health

# Test chat
curl -X POST https://babylike-overtimorously-stacey.ngrok-free.dev/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "query": "What is tax in India?", "session_id": "default"}'

# Test ML health  
curl https://unoperated-merideth-sparklike.ngrok-free.dev/health
```

Expected chat response fields: `response`, `intent`, `session_id`, `memory_used`, `rag_chunks_used`, `confidence`

---

## 🔑 Credentials (from `.env`)

- **MongoDB Atlas URI:** `mongodb+srv://aryanlomte_db_user:...@cluster0.0mw7kni.mongodb.net/`
- **DB Name:** `budget_bandhu`
- **Ngrok Token 1 (somaiya):** `ARYAN_LOMTE_SOMAIYA_EDU_AUTHTOKEN` → ML backend
- **Ngrok Token 2 (gmail):** `LORDAKJ05_GMAIL_COM_AUTHTOKEN` → RAG backend
