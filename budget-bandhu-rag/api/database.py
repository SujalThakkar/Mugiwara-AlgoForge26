"""
MongoDB Database Connection & Configuration
BudgetBandhu ML API

Author: Tanuj
Date: Jan 16, 2026
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
import os

from dotenv import load_dotenv
load_dotenv()
MONGO_URL = os.environ.get("MONGODB_ATLAS_URI")
DATABASE_NAME = os.environ.get("MONGODB_DATABASE", "budget_bandhu")


class Database:
    """Async MongoDB connection manager"""
    
    client: Optional[AsyncIOMotorClient] = None
    
    @classmethod
    async def connect(cls):
        """Connect to MongoDB"""
        import certifi
        print(f"[DATABASE] Connecting to MongoDB at {MONGO_URL}...")
        cls.client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
        
        # Verify connection
        try:
            await cls.client.admin.command('ping')
            print("[DATABASE] MongoDB connection successful!")
        except Exception as e:
            print(f"[DATABASE] Connection failed: {e}")
            raise
    
    @classmethod
    async def disconnect(cls):
        """Disconnect from MongoDB"""
        if cls.client:
            cls.client.close()
            print("[DATABASE] MongoDB connection closed")
    
    @classmethod
    def get_db(cls):
        """Get database instance"""
        return cls.client[DATABASE_NAME]
    
    @classmethod
    def get_collection(cls, collection_name: str):
        """Get a specific collection"""
        return cls.get_db()[collection_name]


# Collection names
COLLECTIONS = {
    "users": "users",
    "transactions": "transactions",
    "budgets": "budgets",
    "goals": "goals",
    "gamification": "gamification"
}


# Dependency for routes
async def get_database():
    """FastAPI dependency to get database"""
    return Database.get_db()
