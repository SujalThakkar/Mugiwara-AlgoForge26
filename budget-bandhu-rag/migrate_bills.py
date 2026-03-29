import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate():
    client = AsyncIOMotorClient(os.environ['MONGODB_ATLAS_URI'], tlsCAFile=certifi.where())
    db = client[os.environ.get('MONGODB_DATABASE', 'budget_bandhu')]
    
    old_id = "7558497556"
    new_id = "917558497556"
    
    # 1. Migrate Bills
    res = await db.bills.update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
    logger.info(f"✅ Migrated {res.modified_count} bills from {old_id} to {new_id}")
    
    # 2. Check if user needs copying
    old_user = await db.users.find_one({"_id": old_id})
    if old_user:
        try:
            # Create a new user with 12-digit ID but same data
            new_user = old_user.copy()
            new_user["_id"] = new_id
            await db.users.insert_one(new_user)
            logger.info(f"✅ Copied user data to {new_id}")
        except Exception:
            logger.info(f"ℹ️ User {new_id} already exists, skipping copy.")

    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
