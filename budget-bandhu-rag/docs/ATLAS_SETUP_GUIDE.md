# BudgetBandhu — MongoDB Atlas Setup Guide

Step-by-step instructions to connect the Financial Cognitive OS to a MongoDB Atlas M0 (free) cluster.

---

## Step 1: Create an Atlas Account and Cluster

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) and sign up / log in.
2. Click **"Build a Database"** → Select **M0 Free Tier**.
3. Choose **Cloud Provider**: AWS, Region: **ap-south-1 (Mumbai)** for lowest India latency.
4. Name your cluster: `Cluster0` (default is fine).
5. Click **"Create"** — takes ~3 minutes to provision.

---

## Step 2: Create a Database User

1. In the left sidebar → **Database Access** → **Add New Database User**.
2. Authentication Method: **Password**.
3. Username: `aryanlomte_db_user` (or any name you choose).
4. Password: generate a strong password and **save it**.
5. Built-in Role: **Read and write to any database**.
6. Click **Add User**.

---

## Step 3: Set Network Access

> [!IMPORTANT]
> For Railway / Render cloud deployment, you must allow all IPs.

1. Left sidebar → **Network Access** → **Add IP Address**.
2. Click **"Allow Access from Anywhere"** → this sets `0.0.0.0/0`.
3. Click **Confirm**.

For local development only, you can use **"Add Current IP"** instead.

---

## Step 4: Get the Connection String

1. Left sidebar → **Database** → **Connect** on your cluster.
2. Choose **"Drivers"** → Language: **Python**, Driver: **motor** (or pymongo 4+).
3. Copy the connection string — it looks like:
   ```
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
4. Replace `<username>` and `<password>` with your credentials from Step 2.

---

## Step 5: Configure Your .env File

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env`:
```env
MONGODB_ATLAS_URI=mongodb+srv://aryanlomte_db_user:<password>@cluster0.0mw7kni.mongodb.net/?appName=Cluster0
MONGODB_DATABASE=budget_bandhu
SQLITE_PATH=working_memory.db
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ATLAS_VECTOR_INDEX_NAME=episodic_vector_index
ATLAS_TEXT_INDEX_NAME=episodic_text_index
```

---

## Step 6: Install Dependencies and Run Migrations

```bash
cd budget-bandhu-ml

# Install all dependencies (creates virtual environment first if needed)
pip install -r requirements.txt

# Run SQLite + Atlas migrations (creates collections + regular indexes)
python -m database.migrations

# Verify setup
python -m database.atlas_migrations --verify
```

Expected output:
```
✓  episodic_memory — created
✓  semantic_memory — created
✓  knowledge_graph_edges — created
✓  procedural_memory — created
✓  trajectory_snapshots — created (time series)
✓  retrieval_audit — created
✓  user_profiles — created
✓  All 7 collections verified
```

---

## Step 7: Create the Vector Search Index (Atlas UI required)

> [!IMPORTANT]
> Atlas $vectorSearch indexes **cannot** be created via Python/Motor. You must use the Atlas UI or mongocli.

1. In Atlas UI → **Database** → Click your cluster → **Browse Collections**.
2. Select database `budget_bandhu`, collection `episodic_memory`.
3. Click **"Search Indexes"** tab → **"Create Search Index"**.
4. Choose **"Atlas Vector Search"** → **"JSON Editor"**.
5. Set index name: `episodic_vector_index`.
6. Paste this JSON:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 384,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "user_id"
    },
    {
      "type": "filter",
      "path": "decay_score"
    }
  ]
}
```

7. Click **"Next"** → **"Create Search Index"**. Takes ~2 minutes.

> **Print all index definitions:** `python -m database.atlas_index_definitions`

---

## Step 8: Create the Full-Text Search Index (Atlas UI required)

1. Same collection `episodic_memory` → **"Search Indexes"** → **"Create Search Index"**.
2. Choose **"Atlas Search"** → **"JSON Editor"**.
3. Set index name: `episodic_text_index`.
4. Paste this JSON:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "trigger_description": {"type": "string", "analyzer": "lucene.english"},
      "outcome_description": {"type": "string", "analyzer": "lucene.english"},
      "category": {"type": "string", "analyzer": "lucene.keyword"},
      "user_id": {"type": "string", "analyzer": "lucene.keyword"}
    }
  }
}
```

5. Repeat for `semantic_memory` collection → index name `semantic_text_index`:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "attribute": {"type": "string", "analyzer": "lucene.english"},
      "value": {"type": "string", "analyzer": "lucene.english"},
      "user_id": {"type": "string", "analyzer": "lucene.keyword"}
    }
  }
}
```

---

## Step 9: Verify the Full Setup

```bash
# Full verification
python -m database.atlas_migrations --verify

# Test Atlas connectivity
python -c "
import asyncio
from database.atlas_client import init_atlas, ping_atlas

async def check():
    await init_atlas()
    ok = await ping_atlas()
    print('Atlas connected:', ok)

asyncio.run(check())
"
```

---

## Step 10: Migrate Existing SQLite Data (if upgrading)

If you have existing data in the old SQLite-only system:

```bash
# Migrate a specific user's episodic + semantic data to Atlas
python -m database.migrations --user <your_user_id>
```

This will:
- Read old SQLite episodic/semantic tables
- Generate embeddings for each record
- Upsert to Atlas in batches of 50
- Print migration summary

---

## Troubleshooting

| Error | Solution |
|-------|---------|
| `ServerSelectionTimeoutError` | Check network access allows your IP (Step 3) |
| `AuthenticationFailed` | Verify username/password in connection string (Step 4) |
| `$vectorSearch index not found` | Create the vector search index in Atlas UI (Step 7) |
| `$search index not found` | Create the text search index in Atlas UI (Step 8) |
| System falls back to SQLite | Atlas unreachable — check connection string and internet |
| Fallback mode active | Check logs for `[FALLBACK]` messages; fix Atlas and restart |

---

## M0 Free Tier Limits

| Limit | Value |
|-------|-------|
| Storage | 512 MB |
| RAM | Shared |
| Max connections | 500 (we use max 50) |
| Transactions | ❌ Not supported (we use optimistic writes) |
| Change streams | ❌ Not on M0 |
| Vector search dimensions | ✅ 384-dim supported |
| Atlas Search | ✅ Supported |
| $graphLookup | ✅ Supported (capped at maxDepth=2) |
