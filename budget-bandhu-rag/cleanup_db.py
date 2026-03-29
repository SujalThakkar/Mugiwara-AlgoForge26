import asyncio
import os
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv() # Load from .env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGO_URI = os.environ.get("MONGODB_ATLAS_URI")
DB_NAME = os.environ.get("MONGODB_DATABASE", "budget_bandhu")

async def sanitize_db():
    import certifi
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    user_id = "917558497556"
    logger.info(f"🧹 Starting cleanup for user: {user_id}")
    
    # 1. Sanitize Transactions
    txns_cursor = db.transactions.find({"user_id": user_id})
    txns = await txns_cursor.to_list(length=10000)
    logger.info(f"Found {len(txns)} transactions")
    
    updates = 0
    for t in txns:
        original_date = t.get("date")
        curr_id = t["_id"]
        
        new_date = None
        
        # Handle various invalid states
        if not original_date or str(original_date).lower() in ("nan", "none", "null", ""):
            new_date = datetime.utcnow().strftime("%Y-%m-%d")
        elif isinstance(original_date, datetime):
            new_date = original_date.strftime("%Y-%m-%d")
        else:
            try:
                # Try common formats
                date_str = str(original_date).split(" ")[0] # Remove time if present
                parsed = None
                
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
                    try:
                        parsed = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                
                if parsed:
                    new_date = parsed.strftime("%Y-%m-%d")
                else:
                    new_date = datetime.utcnow().strftime("%Y-%m-%d") # Last resort
            except Exception:
                new_date = datetime.utcnow().strftime("%Y-%m-%d")
        
        if new_date != original_date:
            await db.transactions.update_one({"_id": curr_id}, {"$set": {"date": new_date}})
            updates += 1
            
    logger.info(f"✅ Updated {updates} transactions with fixed dates.")
    
    # 2. Sanitize Goals (ensure deadline is valid)
    goals_cursor = db.goals.find({"user_id": user_id})
    goals = await goals_cursor.to_list(length=100)
    for g in goals:
        d = g.get("deadline")
        if not d or str(d).lower() in ("nan", "none", ""):
            # Set a default deadline 6 months from now if missing
            default_deadline = (datetime.utcnow().replace(month=(datetime.utcnow().month + 6) % 12 or 1), 1).strftime("%Y-%m-%d")
            # oops, simpler:
            from dateutil.relativedelta import relativedelta
            default_deadline = (datetime.utcnow() + relativedelta(months=6)).strftime("%Y-%m-%d")
            
            await db.goals.update_one({"_id": g["_id"]}, {"$set": {"deadline": default_deadline}})
            logger.info(f"Fixed goal deadline for: {g.get('name')}")

    client.close()
    logger.info("🚀 Cleanup complete!")

if __name__ == "__main__":
    asyncio.run(sanitize_db())
