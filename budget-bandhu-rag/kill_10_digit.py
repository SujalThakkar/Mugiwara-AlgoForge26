import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Wipe")

async def kill_10_digit():
    client = AsyncIOMotorClient(os.environ['MONGODB_ATLAS_URI'], tlsCAFile=certifi.where())
    db = client[os.environ.get('MONGODB_DATABASE', 'budget_bandhu')]
    
    old_id = "7558497556"
    new_id = "917558497556"
    
    colls = await db.list_collection_names()
    logger.info(f"💣 Wiping {old_id} from the face of the DB...")
    
    for coll_name in colls:
        coll = db[coll_name]
        
        # 1. Atomic Update Loop
        async for doc in coll.find({"user_id": old_id}):
            # For each document, try to update it. If it fails (duplicate), just delete it.
            try:
                # We need to use the doc's _id to update specifically
                await coll.update_one({"_id": doc["_id"]}, {"$set": {"user_id": new_id}})
            except Exception:
                # Duplicate! Delete the old one as requested (Scrap it)
                await coll.delete_one({"_id": doc["_id"]})
                logger.info(f"   🗑️ Colliding record in {coll_name} deleted.")
        
        # 2. Key-based doc (_id == 7558... )
        await coll.delete_many({"_id": old_id})
        logger.info(f"✅ [{coll_name}] Cleaned.")

    client.close()
    logger.info("💀 10-digit system is GONE.")

if __name__ == "__main__":
    asyncio.run(kill_10_digit())
