import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()

async def find_bills():
    uri = os.environ.get("MONGODB_ATLAS_URI")
    db_name = os.environ.get("MONGODB_DATABASE", "budget_bandhu")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]
    
    # Common IDs to check
    ids = ["917558497556", "7558497556", "+917558497556", "+7558497556"]
    
    for uid in ids:
        count = await db.bills.count_documents({"user_id": uid})
        print(f"User ID {uid}: {count} bills")
        if count > 0:
            async for b in db.bills.find({"user_id": uid}):
                print(f"  - [{uid}] {b.get('title')} ({b.get('amount')}) at {b.get('due_date')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(find_bills())
