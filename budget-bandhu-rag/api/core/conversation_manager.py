"""
Conversation Manager - MongoDB Version (API Core)
Adapted for api/database.py
"""
from typing import Dict, List, Optional
from datetime import datetime
import uuid
from api.database import Database

class ConversationManager:
    """Manages chat sessions in MongoDB"""
    
    @property
    def conversations(self):
        return Database.get_db()["conversations"]
    
    async def create_session(self, mobile_number: str) -> str:
        """Create new session"""
        session_id = str(uuid.uuid4())
        doc = {
            "session_id": session_id,
            "user_id": mobile_number,
            "started_at": datetime.utcnow(),
            "messages": []
        }
        await self.conversations.insert_one(doc)
        return session_id
    
    async def add_message(self, session_id: str, role: str, content: str, confidence: float = 1.0, metadata: Optional[Dict] = None):
        """Add message"""
        msg = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
            "confidence": confidence,
            "meta_data": metadata or {}
        }
        await self.conversations.update_one(
            {"session_id": session_id},
            {"$push": {"messages": msg}, "$set": {"last_active": datetime.utcnow()}}
        )
    
    async def get_conversation_history(self, session_id: str, limit: int = 6) -> List[Dict]:
        """Get history"""
        doc = await self.conversations.find_one({"session_id": session_id}, {"messages": 1})
        if not doc or "messages" not in doc:
            return []
        
        messages = doc["messages"][-limit:] if limit else doc["messages"]
        return [{"role": m["role"], "content": m["content"], "timestamp": m["timestamp"].isoformat()} for m in messages]
