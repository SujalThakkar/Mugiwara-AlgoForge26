import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check_episodic():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    docs = await db['episodic_memory'].find({"user_id": "917558497556"}).sort("created_at", -1).limit(10).to_list(10)
    print("Latest 10 EPISODIC memories:")
    for d in docs:
        print(f"{d.get('trigger_description')} | {d.get('amount_inr')} | {d.get('category')} | {d.get('event_type')}")

    client.close()

if __name__ == '__main__':
    asyncio.run(check_episodic())
