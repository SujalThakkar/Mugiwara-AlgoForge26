"""
Memory Manager - Bridge between Agent and MongoDB (API Core Version)
Adapted for api/database.py
"""
from typing import Dict, List, Optional
from datetime import datetime
from api.database import Database

class MemoryManager:
    """
    Simplified memory interface for agent controller.
    """
    
    def __init__(self):
        # Database.get_collection gets the collection directly
        pass # Database is static/singleton
    
    @property
    def memories_collection(self):
        return Database.get_db()["memories"]

    @property
    def users_collection(self):
        return Database.get_db()["users"]
    
    async def get_user_memories(self, mobile_number: str, limit: int = 10) -> Dict:
        """Retrieve all memories for a user (semantic + episodic)"""
        # Semantic
        semantic_cursor = self.memories_collection.find(
            {"user_id": mobile_number, "type": "semantic"}
        ).sort("updated_at", -1).limit(limit)
        
        semantic = []
        async for mem in semantic_cursor:
            semantic.append({
                'attribute_type': mem['attribute_type'],
                'value': mem['value'],
                'updated_at': mem['updated_at'].isoformat()
            })
            
        # Episodic
        episodic_cursor = self.memories_collection.find(
            {"user_id": mobile_number, "type": "episodic"}
        ).sort("timestamp", -1).limit(limit)
        
        episodic = []
        async for mem in episodic_cursor:
            episodic.append({
                'event_summary': mem['event_summary'],
                'trigger_type': mem['trigger_type'],
                'timestamp': mem['timestamp'].isoformat(),
                'metadata': mem.get('meta_data', {})
            })
            
        return {'semantic': semantic, 'episodic': episodic}
    
    async def store_semantic_memory(self, mobile_number: str, attribute_type: str, value: str) -> str:
        """Store semantic memory"""
        # Note: We rely on User endpoints for user creation, but here we can ensure minimal user
        # Upsert
        result = await self.memories_collection.update_one(
            {"user_id": mobile_number, "type": "semantic", "attribute_type": attribute_type},
            {"$set": {"value": value, "updated_at": datetime.utcnow()}},
            upsert=True
        )
        return str(result.upserted_id or "updated")

    async def store_episodic_memory(self, mobile_number: str, event_summary: str, trigger_type: str, metadata: Optional[Dict] = None) -> str:
        """Store episodic memory"""
        doc = {
            "user_id": mobile_number,
            "type": "episodic",
            "event_summary": event_summary,
            "trigger_type": trigger_type,
            "meta_data": metadata or {},
            "timestamp": datetime.utcnow(),
            "relevance_score": 1.0
        }
        result = await self.memories_collection.insert_one(doc)
        return str(result.inserted_id)
