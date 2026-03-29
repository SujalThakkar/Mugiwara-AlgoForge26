import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def update_income():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    for uid in ['7558497556', '917558497556']:
        res = await db['users'].update_many(
            {'_id': uid}, 
            {'$set': {'income': 50090}}
        )
        print(f"Matched {uid}:", res.matched_count, 'Modified:', res.modified_count)

    client.close()

if __name__ == '__main__':
    asyncio.run(update_income())
