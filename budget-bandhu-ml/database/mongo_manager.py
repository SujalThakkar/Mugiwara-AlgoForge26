"""
MongoDB Manager - Async Database Layer
Handles connection and CRUD operations for MongoDB.

Primary Key: Mobile Number (String)

Author: Aryan Lomte
Date: Jan 16, 2026
"""
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class MongoManager:
    """
    Async MongoDB wrapper for Budget Bandhu.
    """
    
    def __init__(self, connection_string: str = None, db_name: str = "budget_bandhu"):
        self.connection_string = connection_string or os.getenv("MONGODB_URL", "mongodb://localhost:27017")
        self.db_name = db_name
        self.client: AsyncIOMotorClient = None
        self.db = None
        
        # Collections
        self.users = None
        self.memories = None
        self.conversations = None
        self.messages = None
        self.transactions = None
        
    async def connect(self):
        """Initialize connection to MongoDB"""
        try:
            logger.info(f"[MONGO] Connecting to {self.db_name}...")
            self.client = AsyncIOMotorClient(self.connection_string)
            self.db = self.client[self.db_name]
            
            # Initialize collections
            self.users = self.db.users
            self.memories = self.db.memories
            self.conversations = self.db.conversations
            self.messages = self.db.messages  # Optional: Could embed in conversations
            
            # Create Indexes
            await self._create_indexes()
            
            # ping
            await self.client.admin.command('ping')
            logger.info("[MONGO] ✅ Connected successfully")
            
        except Exception as e:
            logger.error(f"[MONGO] ❌ Connection failed: {e}")
            raise e
            
    async def _create_indexes(self):
        """Create necessary indexes for performance"""
        # User ID is the mobile number (primary key)
        # users collection uses _id as mobile_number naturally
        
        # Memories: Query by user_id + types
        await self.memories.create_index([("user_id", 1), ("type", 1)])
        await self.memories.create_index([("user_id", 1), ("timestamp", -1)])
        
        # Conversations
        await self.conversations.create_index([("session_id", 1)], unique=True)
        await self.conversations.create_index([("user_id", 1)])
        
        logger.info("[MONGO] Indexes created")

    async def close(self):
        """Close connection"""
        if self.client:
            self.client.close()
            logger.info("[MONGO] Connection closed")

    # --- USER OPERATIONS ---
    
    async def get_user(self, mobile_number: str) -> Optional[Dict]:
        """Get user by mobile number"""
        return await self.users.find_one({"_id": mobile_number})
    
    async def create_or_update_user(self, mobile_number: str, data: Dict = None):
        """Create user if not exists"""
        update_data = {
            "$set": {
                "last_active": datetime.utcnow(),
                # Merge additional data if provided
                **(data or {})
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow()
            }
        }
        await self.users.update_one(
            {"_id": mobile_number},
            update_data,
            upsert=True
        )

# Global Instance
db = MongoManager()
