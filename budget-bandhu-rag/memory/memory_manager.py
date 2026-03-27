"""
Memory Manager - Bridge between Agent and MongoDB
Simplifies memory operations for the agent controller.

Author: Aryan Lomte
Date: Jan 16, 2026
"""
from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
logger = logging.getLogger(__name__)

from database.mongo_manager import MongoManager

class MemoryManager:
    """
    Simplified memory interface for agent controller.
    Wraps MongoDB operations into simple get/store methods.
    """
    
    def __init__(self, db_manager: MongoManager):
        """
        Initialize memory manager with MongoManager instance
        """
        self.db = db_manager
        print(f"[MEMORY] Manager initialized with MongoDB")
    
    async def get_user_memories(self, mobile_number: str, limit: int = 10) -> Dict:
        """
        Retrieve all memories for a user (semantic + episodic)
        
        Args:
            mobile_number: User Primary Key (Mobile)
            limit: Max memories per type
        
        Returns:
            {
                'semantic': List[Dict],
                'episodic': List[Dict]
            }
        """
        # Semantic Memories (User Profile)
        # Stored as type="semantic" in 'memories' collection
        semantic_cursor = self.db.memories.find(
            {"user_id": mobile_number, "type": "semantic"}
        ).sort("updated_at", -1).limit(limit)
        
        semantic = []
        async for mem in semantic_cursor:
            semantic.append({
                'attribute_type': mem['attribute_type'],
                'value': mem['value'],
                'updated_at': mem['updated_at'].isoformat()
            })
            
        # Episodic Memories (Events)
        logger.info(f"[MEMORY] Fetching memories for {mobile_number}")
        episodic_cursor = self.db.memories.find(
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
        
        logger.info(f"[MEMORY] Found {len(episodic)} explicit memories")
            
        # Virtual Episodic Memories (RAW Transactions)
        # Pulling recent raw transactions to give agent immediate context
        logger.info(f"[MEMORY] Checking transactions attribute: {hasattr(self.db, 'transactions')}")
        if hasattr(self.db, 'transactions') and self.db.transactions is not None:
            txn_cursor = self.db.transactions.find(
                {"user_id": mobile_number}
            ).sort("date", -1).limit(limit)
            
            txn_count = 0
            async for txn in txn_cursor:
                txn_count += 1
                # Format as a pseudo-episodic memory
                date_str = txn['date'].isoformat() if isinstance(txn.get('date'), datetime) else str(txn.get('date'))
                summary = f"Transaction: {txn.get('description')} | Amount: {txn.get('amount')} | Category: {txn.get('category', 'Uncategorized')}"
                if txn.get('is_anomaly'):
                    summary += " (ANOMALY DETECTED)"
                
                episodic.append({
                    'event_summary': summary,
                    'trigger_type': 'transaction',
                    'timestamp': date_str,
                    'metadata': {
                        'amount': txn.get('amount'),
                        'category': txn.get('category'),
                        'type': txn.get('type')
                    }
                })
            logger.info(f"[MEMORY] Added {txn_count} virtual memories from transactions")
        else:
            logger.warning("[MEMORY] Transactions collection NOT AVAILABLE in db manager")
            
        return {
            'semantic': semantic,
            'episodic': episodic
        }
    
    async def store_semantic_memory(
        self,
        mobile_number: str,
        attribute_type: str,
        value: str,
        confidence: float = 1.0
    ) -> str:
        """
        Store or update user profile attribute
        """
        # Upsert user first
        await self.db.create_or_update_user(mobile_number)
        
        # Update/Insert Semantic Memory
        result = await self.db.memories.update_one(
            {
                "user_id": mobile_number,
                "type": "semantic",
                "attribute_type": attribute_type
            },
            {
                "$set": {
                    "value": value,
                    "confidence": confidence,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        if result.upserted_id:
            memory_id = str(result.upserted_id)
        else:
            # Needed to get ID if updated
            doc = await self.db.memories.find_one({
                "user_id": mobile_number, 
                "attribute_type": attribute_type
            })
            memory_id = str(doc['_id'])
            
        print(f"[MEMORY] Stored semantic {attribute_type} for {mobile_number}")
        return memory_id
    
    async def store_episodic_memory(
        self,
        mobile_number: str,
        event_summary: str,
        trigger_type: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Store an event/transaction
        """
        # Ensure user exists
        await self.db.create_or_update_user(mobile_number)
        
        doc = {
            "user_id": mobile_number,
            "type": "episodic",
            "event_summary": event_summary,
            "trigger_type": trigger_type,
            "meta_data": metadata or {},  # Store as direct JSON object in Mongo
            "timestamp": datetime.utcnow(),
            "relevance_score": 1.0
        }
        
        result = await self.db.memories.insert_one(doc)
        memory_id = str(result.inserted_id)
        
        print(f"[MEMORY] Stored episodic event for {mobile_number}")
        return memory_id
    
    async def get_total_users(self) -> int:
        return await self.db.users.count_documents({})
    
    async def get_total_memories(self) -> int:
        return await self.db.memories.count_documents({})
