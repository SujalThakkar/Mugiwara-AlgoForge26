import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from core.agent_controller import AgentController

load_dotenv()

async def ingest_transactions():
    print("🚀 Initializing AI models for embedding...")
    ctrl = AgentController()
    
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    # 1. Fetch the 100 transactions from the CSV upload
    docs = await db['transactions'].find({"user_id": "917558497556"}).sort("date", -1).to_list(200)
    print(f"📦 Found {len(docs)} transactions for user 917558497556. Starting vector ingestion...")
    
    count = 0
    for txn in docs:
        event_type = "EXPENSE" if txn.get('type') == 'debit' else "INCOME"
        amount = float(txn.get('amount', 0.0))
        date_str = str(txn.get('date'))
        desc = str(txn.get('description'))
        cat = str(txn.get('category'))
        
        # 2. Store in episodic memory
        ep_id = await ctrl.episodic.store_episode(
            user_id="917558497556",
            event_type=event_type,
            trigger_description=f"Transaction on {date_str}: {desc} ({cat})",
            outcome_description="CSV Uploaded raw transaction.",
            amount_inr=amount,
            category=cat
        )
        count += 1
        if count % 10 == 0:
            print(f"✅ Ingested {count}/{len(docs)} vectors...")

    print("🎉 Sync Complete! The AI now has access to the 3-month CSV history in its Episodic Memory.")
    client.close()

if __name__ == '__main__':
    asyncio.run(ingest_transactions())
