import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def update_semantic_income():
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    # Update the semantic_memory collection
    res = await db['semantic_memory'].update_many(
        {
            'user_id': '917558497556',
            'attribute': 'monthly_income'
        }, 
        {'$set': {'value': '₹50090', 'confidence_score': 1.0}}
    )
    print('Semantic memory Matched:', res.matched_count, 'Modified:', res.modified_count)

    client.close()

if __name__ == '__main__':
    asyncio.run(update_semantic_income())
