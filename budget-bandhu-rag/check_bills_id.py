import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()

async def check():
    uri = os.environ.get("MONGODB_ATLAS_URI")
    db_name = os.environ.get("MONGODB_DATABASE", "budget_bandhu")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]
    
    b12 = await db.bills.count_documents({"user_id": "917558497556"})
    b10 = await db.bills.count_documents({"user_id": "7558497556"})
    
    print(f"12-digit ID (917558497556) Bills: {b12}")
    print(f"10-digit ID (7558497556) Bills: {b10}")
    
    if b10 > 0:
        latest = await db.bills.find_one({"user_id": "7558497556"}, sort=[("_id", -1)])
        print(f"Latest 10-digit Bill: {latest.get('title')} - {latest.get('amount')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check())
