import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check_transactions():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    docs = await db['transactions'].find({"user_id": "917558497556", "category": "Food & Dining"}).sort("date", -1).limit(5).to_list(5)
    print("Latest 5 food transactions:")
    for d in docs:
        amount = d.get('amount')
        desc = d.get('description', '')
        date = d.get('date', '')
        print(f"{date} | {desc} | {amount}")

    client.close()

if __name__ == '__main__':
    asyncio.run(check_transactions())
