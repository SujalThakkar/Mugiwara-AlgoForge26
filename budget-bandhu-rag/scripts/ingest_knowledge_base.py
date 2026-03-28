"""
scripts/ingest_knowledge_base.py
Ingests all india_finance JSON files into MongoDB Atlas knowledge_base collection.
Run once (or after KB updates): python scripts/ingest_knowledge_base.py
"""
import json, os, glob, asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import certifi
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI  = os.environ.get("MONGODB_ATLAS_URI", os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
DB_NAME      = os.environ.get("MONGODB_DATABASE", "budget_bandhu")
KB_DIR       = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "india_finance")


async def ingest():
    from pymongo.server_api import ServerApi
    client = AsyncIOMotorClient(
        MONGODB_URI,
        maxPoolSize=5,
        minPoolSize=1,
        maxIdleTimeMS=30000,
        heartbeatFrequencyMS=10000,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=10000,
        socketTimeoutMS=15000,
        retryWrites=True,
        retryReads=True,
        server_api=ServerApi("1")
    )
    db     = client[DB_NAME]
    coll   = db["knowledge_base"]

    # Clear existing KB (full refresh)
    deleted = await coll.delete_many({"source": "india_finance"})
    print(f"[INGEST] Cleared {deleted.deleted_count} existing KB chunks")

    files   = glob.glob(os.path.join(KB_DIR, "*.json"))
    total   = 0
    docs    = []

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        doc_id   = data.get("document_id", os.path.basename(fpath))
        source   = data.get("source", "india_finance")
        category = data.get("category", "general")

        for chunk in data.get("chunks", []):
            docs.append({
                "document_id": doc_id,
                "chunk_id":    chunk["id"],
                "source":      source,
                "category":    category,
                "text":        chunk["text"],
                "tags":        chunk.get("tags", []),
                "ingested_at": datetime.utcnow().isoformat()
            })
            total += 1

    if docs:
        result = await coll.insert_many(docs)
        print(f"[INGEST] ✅ Inserted {len(result.inserted_ids)} chunks across {len(files)} files")

    # Print summary
    by_category = {}
    for d in docs:
        cat = d["category"]
        by_category[cat] = by_category.get(cat, 0) + 1
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s}: {count} chunks")

    client.close()


if __name__ == "__main__":
    asyncio.run(ingest())
