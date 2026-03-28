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
        try:
            session_id = str(uuid.uuid4())
            
            doc = {
                "session_id": session_id,
                "user_id": mobile_number,
                "started_at": datetime.utcnow(),
                "messages": []
            }
            
            await self.db.conversations.insert_one(doc)
            print(f"[CONV] Created session {session_id} for {mobile_number}")
            
            return session_id
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(f"[CONV] create_session failed (non-blocking): {e}")
            return "default"
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        confidence: float = 1.0,
        metadata: Optional[Dict] = None
    ):
        """Add message to session"""
        try:
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
                    "$set": {"last_active": datetime.utcnow()},
                    "$setOnInsert": {"session_id": session_id}
                },
                upsert=True
            )
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(
                f"[CONV] add_message failed (non-blocking): {type(e).__name__}: {str(e)[:100]}"
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
        try:
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
                    "timestamp": msg["timestamp"].isoformat() if hasattr(msg["timestamp"], 'isoformat') else msg["timestamp"]
                }
                for msg in messages
            ]
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(f"[CONV] get_conversation_history failed: {e}")
            return []

    async def get_history(self, session_id: str, limit: int = 6) -> List[Dict]:
        """Alias for get_conversation_history"""
        return await self.get_conversation_history(session_id, limit)

    async def get_turn_count(self, session_id: str) -> int:
        """Get the number of message turns in the session"""
        try:
            doc = await self.db.conversations.find_one(
                {"session_id": session_id},
                {"messages": 1}
            )
            if not doc or "messages" not in doc:
                return 0
            return len(doc["messages"]) // 2  # Assuming 2 messages per turn roughly
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(f"[CONV] get_turn_count failed: {e}")
            return 0

    async def build_context_from_history(self, session_id: str, max_messages: int = 6) -> List[Dict]:
        """Alias for build context compatibility"""
        return await self.get_conversation_history(session_id, limit=max_messages)

    async def get_user_sessions(self, mobile_number: str) -> List[str]:
        """Get all session IDs for a user"""
        try:
            cursor = self.db.conversations.find(
                {"user_id": mobile_number},
                {"session_id": 1, "started_at": 1}
            ).sort("started_at", -1).limit(5)
            
            sessions = []
            async for doc in cursor:
                sessions.append(doc["session_id"])
            return sessions
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(f"[CONV] get_user_sessions failed: {e}")
            return []
    
    async def end_session(self, session_id: str):
        """Mark session as ended"""
        try:
            await self.db.conversations.update_one(
                {"session_id": session_id},
                {"$set": {"status": "ended", "ended_at": datetime.utcnow()}}
            )
        except Exception as e:
            import logging
            logging.getLogger("BudgetBandhu").warning(f"[CONV] end_session failed: {e}")
