import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migrator")

async def migrate_all():
    client = AsyncIOMotorClient(os.environ['MONGODB_ATLAS_URI'], tlsCAFile=certifi.where())
    db = client[os.environ.get('MONGODB_DATABASE', 'budget_bandhu')]
    
    old_id = "7558497556"
    new_id = "917558497556"
    
    collections = [
        "episodic_memory", "semantic_memory", "conversations", 
        "bills", "transactions", "budgets", "goals", "tax_investments"
    ]
    
    logger.info(f"🚀 Starting global migration from {old_id} to {new_id}...")
    
    for coll in collections:
        try:
            res = await db[coll].update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
            logger.info(f"✅ [{coll}] Migrated {res.modified_count} documents.")
        except Exception as e:
            logger.error(f"❌ [{coll}] Migration failed: {e}")
            
    # Special case: users collection uses _id as the phone number
    try:
        old_user = await db["users"].find_one({"_id": old_id})
        if old_user:
            new_check = await db["users"].find_one({"_id": new_id})
            if not new_check:
                old_user["_id"] = new_id
                await db["users"].insert_one(old_user)
                await db["users"].delete_one({"_id": old_id})
                logger.info(f"👤 Copied user profile to {new_id}")
            else:
                logger.info(f"👤 User {new_id} already exists, skipping profile copy.")
    except Exception as e:
        logger.error(f"❌ [users] Migration failed: {e}")

    client.close()
    logger.info("🏁 Global migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_all())
