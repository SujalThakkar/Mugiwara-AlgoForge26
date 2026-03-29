import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check_transactions():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    docs_10 = await db['transactions'].find({"user_id": "7558497556"}).to_list(100)
    print("Total Txns for 10-digit ID 7558497556:", len(docs_10))
    if docs_10:
        for d in sorted(docs_10, key=lambda x: str(x.get('date')), reverse=True)[:5]:
            print(f"{d.get('date')} | {d.get('description')} | {d.get('amount')} | {d.get('category')}")

    docs_12 = await db['transactions'].find({"user_id": "917558497556"}).to_list(100)
    print("\nTotal Txns for 12-digit ID 917558497556:", len(docs_12))

    client.close()

if __name__ == '__main__':
    asyncio.run(check_transactions())
