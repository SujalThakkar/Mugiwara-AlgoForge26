import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def get_cats():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    cats = await db['transactions'].distinct('category', {'user_id': '917558497556'})
    print("Categories:", cats)
    client.close()

if __name__ == '__main__':
    asyncio.run(get_cats())
