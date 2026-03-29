import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ForceSync")

async def force_sync():
    client = AsyncIOMotorClient(os.environ['MONGODB_ATLAS_URI'], tlsCAFile=certifi.where())
    db = client[os.environ.get('MONGODB_DATABASE', 'budget_bandhu')]
    
    old_id = "7558497556"
    new_id = "917558497556"
    
    # Get all collection names
    colls = await db.list_collection_names()
    
    logger.info(f"🔥 SCRAPPING 10-DIGIT SYSTEM ({old_id} -> {new_id})")
    
    for coll_name in colls:
        coll = db[coll_name]
        
        # 1. Update user_id field
        res = await coll.update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
        if res.modified_count > 0:
            logger.info(f"✅ [{coll_name}] Updated {res.modified_count} user_id fields.")
            
        # 2. Update _id field (requires copy-and-delete)
        async for doc in coll.find({"_id": old_id}):
            logger.info(f"🔄 [{coll_name}] Moving _id primary record...")
            try:
                new_doc = doc.copy()
                new_doc["_id"] = new_id
                await coll.insert_one(new_doc)
                await coll.delete_one({"_id": old_id})
                logger.info(f"   ✨ Successfully moved primary record in {coll_name}")
            except Exception as e:
                logger.warning(f"   ⚠️ Primary record move failed (already exists?): {e}")

    # 3. Final cleanup: Find any stray 10-digit IDs in nested values or strings
    # (Aggressive check for the user's specific screenshot)
    res = await db["semantic_memory"].update_many(
        {"user_id": old_id}, 
        {"$set": {"user_id": new_id}}
    )
    logger.info(f"📦 Final semantic cleanup: {res.modified_count} docs.")

    client.close()
    logger.info("💀 10-digit system has been PURGED.")

if __name__ == "__main__":
    asyncio.run(force_sync())
