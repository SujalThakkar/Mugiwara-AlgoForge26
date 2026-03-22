"""
Conversation Manager - MongoDB Version
Manages multi-turn chat history.

Author: Aryan Lomte
Date: Jan 16, 2026
"""
from typing import Dict, List, Optional
from datetime import datetime
import uuid
import json
from database.mongo_manager import MongoManager

class ConversationManager:
    """
    Manages chat sessions and message history in MongoDB.
    """
    
    def __init__(self, db_manager: MongoManager):
        self.db = db_manager
    
    async def create_session(self, mobile_number: str) -> str:
        """Create new conversation session"""
        session_id = str(uuid.uuid4())
        
        doc = {
            "session_id": session_id,
            "user_id": mobile_number,
            "started_at": datetime.utcnow(),
            "messages": []  # Embedded messages pattern for simplicity
        }
        
        await self.db.conversations.insert_one(doc)
        print(f"[CONV] Created session {session_id} for {mobile_number}")
        
        return session_id
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ):
        """Add message to session"""
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
            "confidence": confidence,
            "meta_data": metadata or {}
        }
        
        await self.db.conversations.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message},
                "$set": {"last_active": datetime.utcnow()}
            }
        )
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 6
    ) -> List[Dict]:
        """
        Get conversation history for context building.
        Returns last N messages.
        """
        doc = await self.db.conversations.find_one(
            {"session_id": session_id},
            {"messages": 1}
        )
        
        if not doc or "messages" not in doc:
            return []
            
        # Get last N messages
        messages = doc["messages"][-limit:] if limit else doc["messages"]
        
        # Format for context
        return [
            {
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg["timestamp"].isoformat()
            }
            for msg in messages
        ]

    async def build_context_from_history(self, session_id: str, max_messages: int = 6) -> List[Dict]:
        """Alias for build context compatibility"""
        return await self.get_conversation_history(session_id, limit=max_messages)

    async def get_user_sessions(self, mobile_number: str) -> List[str]:
        """Get all session IDs for a user"""
        cursor = self.db.conversations.find(
            {"user_id": mobile_number},
            {"session_id": 1, "started_at": 1}
        ).sort("started_at", -1).limit(5)
        
        sessions = []
        async for doc in cursor:
            sessions.append(doc["session_id"])
        return sessions
    
    async def end_session(self, session_id: str):
        """Mark session as ended"""
        await self.db.conversations.update_one(
            {"session_id": session_id},
            {"$set": {"status": "ended", "ended_at": datetime.utcnow()}}
        )
