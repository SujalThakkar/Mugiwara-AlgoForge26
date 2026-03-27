# BudgetBandhu — End-to-End Backend Architecture & Flow

This document explains **exactly** how the current backend works, from the moment a user sends a WhatsApp message to the final response they receive.

---

## 🏗️ 1. The Core Infrastructure

### A. Ngrok (The Public Tunnel)
Local development servers (`localhost:8000`) cannot be reached by the internet. Twilio needs a public HTTPS URL to send webhooks to when a user messages the WhatsApp bot.
* **What we do**: We run `ngrok http 8000`.
* **Result**: Ngrok gives us a temporary public URL (e.g., `https://1234-abc.ngrok-free.app`).
* **Why**: This URL bridges the gap between Twilio's cloud and our local FastAPI server.

### B. Twilio (The WhatsApp Gateway)
Twilio handles the official WhatsApp Business API.
* **Setup**: In the Twilio Sandbox, we set the webhook URL to our Ngrok address: `https://1234-abc.ngrok-free.app/whatsapp/webhook`.
* **Action**: When a user texts `whatsapp:+14155238886`, Twilio packages that message into an HTTP POST request and fires it at our Ngrok URL.

---

## ⚡ 2. The Request Journey (A to Z)

### Step 1: Ingress & Verification (`FastAPI /whatsapp/webhook`)
1. **Reception**: The POST request arrives at our FastAPI app (`app.py` -> `routes.py`).
2. **Parsing**: We extract the sender's phone number (`From`) and the message text (`Body`).
3. **User Binding**: We map the phone number to an internal `user_id`. (If they don't exist, we create a new profile in MongoDB).

### Step 2: Intent Classification & Entity Extraction
Before doing anything, the LLM analyzes the raw text.
1. **Query Intent**: Is this a `SIMPLE_LOOKUP` ("How much did I spend?"), `TREND_ANALYSIS` ("Am I spending more this month?"), or `BEHAVIORAL` ("Why can't I save money?")
2. **Parsing**: We extract entities (e.g., amounts, categories, dates).

### Step 3: The 5-Tier Memory Retrieval (`cognitive_memory_manager.py`)
This is the brain of BudgetBandhu. Based on the *Intent*, the manager fetches context from **MongoDB Atlas M0**:

* **Tier 1 (Working)**: SQLite. Recent chat messages in this session.
* **Tier 2 (Episodic)**: Atlas `$vectorSearch` + `$search`. Past specific events ("Spent 3k on Zomato").
* **Tier 3 (Semantic & KG)**: Atlas `$search` + `$graphLookup`. Learned facts ("Salary is 50k", "Food competes with Savings").
* **Tier 4 (Procedural)**: Atlas `$match`. Behavioral strategies (e.g., "Use gentle tone for impulse spenders").
* **Tier 5 (Trajectory)**: Atlas Time Series. Weekly behavior snapshots (Savings rate, spending velocity).

### Step 4: The LangGraph Agent (`budget_bandhu_pipeline.py`)
The retrieved memory + the user's message is fed into a **ReAct (Reason + Act)** Agent loop:

1. **Reasoning**: The LLM looks at the context. "The user is an impulse spender. They spent 5k on food. The procedural memory says to use a *gentle* tone."
2. **Tool Calling**: If data is missing missing, the agent triggers Python tools:
   * `query_transactions()` -> Hits the SQLite transaction DB.
   * `calculate_budget_burn()` -> Math operations.
3. **Execution**: The tools return raw data (e.g., "Total food spend: 12,000").
4. **Synthesis**: The LLM writes the final natural language response applying the behavioral constraints.

### Step 5: Memory Consolidation
Before replying to the user, the system updates its memory:
1. **New Episodes**: The current interaction is stored in Tier 1 (Working).
2. **Important facts**: If the user said something new ("I got promoted"), it's written to Tier 3 (Semantic) in Atlas.
3. **EMA Updates**: If the user reacted positively to the response, the procedural strategy's success rate is mathematically increased in Atlas via `$set`.

### Step 6: Egress (`Twilio Response`)
1. The FastAPI router wraps the final string in TwiML (Twilio XML format).
2. The HTTP response is sent back through the Ngrok tunnel to Twilio.
3. Twilio delivers the message to the user's WhatsApp.

---

## 💾 3. Data Storage Architecture

To stay within the **free tier limits**, we use a hybrid model:

| Data Type | Storage | Mechanism | Why? |
|-----------|---------|-----------|------|
| **Transactions** | SQLite | `SQLAlchemy` | High volume, low latency, easy aggregate math. |
| **Working Memory** | SQLite | `aiosqlite` | Short-term context, cleared often. |
| **Episodic Memory** | Atlas M0 | `$vectorSearch` | Requires semantic similarity (HNSW vectors). |
| **Semantic Memory** | Atlas M0 | `$search` (BM25) | Text-based fact answering. |
| **Knowledge Graph** | Atlas M0 | `$graphLookup` | Up to 2-hop relationship mapping. |
| **Procedural Memory** | Atlas M0 | Standard Index | Quick lookup for `success_rate`. |
| **Failover** | SQLite | `AtlasFallbackBridge` | If Atlas is down, system degrades gracefully. |

---

## 🚀 4. How to Run It Right Now

1. **Start Ngrok** (Terminal 1)
   ```bash
   ngrok http 8000
   ```
   *Copy the `https://...` URL into your Twilio Sandbox Webhook settings.*

2. **Start Ollama** (Terminal 2)
   ```bash
   ollama serve
   # Make sure your model (e.g., llama3 or chosen model) is pulled
   ```

3. **Start the FastAPI Backend** (Terminal 3)
   ```bash
   cd budget-bandhu-ml
   venv\Scripts\activate
   python app.py
   ```
   *(Ensure your `.env` has the `MONGODB_ATLAS_URI`, `TWILIO_` credentials, and `ENABLE_NGROK=True`)*
