import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()

async def verify():
    uri = os.environ.get("MONGODB_ATLAS_URI")
    db_name = os.environ.get("MONGODB_DATABASE", "budget_bandhu")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]
    
    user_id = "917558497556"
    total = await db.transactions.count_documents({"user_id": user_id})
    anomalies = await db.transactions.count_documents({"user_id": user_id, "is_anomaly": True})
    
    print(f"User: {user_id}")
    print(f"Total Transactions: {total}")
    print(f"Total Anomalies: {anomalies}")
    
    if total > 0:
        sample = await db.transactions.find_one({"user_id": user_id})
        print(f"Sample Date: {sample.get('date')}")
        print(f"Sample Category: {sample.get('category')}")
        
    goals = await db.goals.find({"user_id": user_id}).to_list(length=10)
    print(f"Goals found: {len(goals)}")
    for g in goals:
        print(f"- {g.get('name')} (Priority: {g.get('priority')})")

    client.close()

if __name__ == "__main__":
    asyncio.run(verify())
