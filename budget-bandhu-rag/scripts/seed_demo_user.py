from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from dotenv import load_dotenv
import copy

load_dotenv()

async def seed():
    mongo_url = os.environ.get("MONGODB_ATLAS_URI")
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get("MONGODB_DATABASE", "budget_bandhu")]
    
    # Seed baseline so anomaly detector has history
    base_transactions = [
        {"user_id": "+91-9876543210", "description": "Swiggy", 
         "amount": 350, "category": "Food & Dining", "transaction_type": "Debit"},
        {"user_id": "+91-9876543210", "description": "BigBasket",
         "amount": 800, "category": "Groceries", "transaction_type": "Debit"},
        {"user_id": "+91-9876543210", "description": "Salary",
         "amount": 50000, "category": "Salary", "transaction_type": "Credit"},
    ]
    
    baseline = []
    for _ in range(15):
        baseline.extend([copy.deepcopy(t) for t in base_transactions])
        
    await db.transactions.insert_many(baseline)
    print("✅ Seeded 45 baseline transactions")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(seed())
