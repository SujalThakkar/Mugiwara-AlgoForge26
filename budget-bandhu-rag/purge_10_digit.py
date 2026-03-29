import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TotalPurge")

async def purge_10_digit():
    client = AsyncIOMotorClient(os.environ['MONGODB_ATLAS_URI'], tlsCAFile=certifi.where())
    db = client[os.environ.get('MONGODB_DATABASE', 'budget_bandhu')]
    
    old_id = "7558497556"
    new_id = "917558497556"
    
    colls = await db.list_collection_names()
    logger.info(f"💣 TOTAL PURGE OF {old_id} IN PROGRESS...")
    
    for coll_name in colls:
        coll = db[coll_name]
        
        # 1. Update any user_id field
        res = await coll.update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
        if res.modified_count > 0:
            logger.info(f"✅ [{coll_name}] Forced {res.modified_count} user_id updates.")
            
        # 2. Check for the 10-digit ID as a primary _id
        doc = await coll.find_one({"_id": old_id})
        if doc:
            logger.info(f"🔍 Found 10-digit primary record in {coll_name}. Merging...")
            # Does the 12-digit exist?
            existing = await coll.find_one({"_id": new_id})
            if not existing:
                # Move it
                new_doc = doc.copy()
                new_doc["_id"] = new_id
                await coll.insert_one(new_doc)
                logger.info(f"   ✨ Successfully moved record to {new_id}")
            else:
                logger.info(f"   ✅ 12-digit version already exists. Deleting redundant 10-digit record.")
            
            # Now delete the 10-digit one
            await coll.delete_one({"_id": old_id})
            logger.info(f"   🗑️ Purged {old_id} from {coll_name}")

    client.close()
    logger.info("💀 THE 10-DIGIT SYSTEM HAS BEEN EXTERMINATED.")

if __name__ == "__main__":
    asyncio.run(purge_10_digit())
