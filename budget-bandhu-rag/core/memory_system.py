"""
Memory System - The Foundation of Agentic AI
Implements episodic, semantic, and short-term memory with strict retrieval caps.

Author: Aryan Lomte
Date: Jan 13, 2026
"""
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import sqlite3  # Using SQLite for now; Aditya will swap to Postgres later

from intelligence.base import MemoryProvider

class TriggerType(Enum):
    """Episodic memory trigger types"""
    OVERSPEND = "overspend"
    IGNORED_NUDGE = "ignored_nudge"
    CORRECTION = "correction"
    SUCCESS = "success"
    ANOMALY = "anomaly"
    GOAL_EVENT = "goal_event"

class AttributeType(Enum):
    """Semantic memory attribute types"""
    INCOME_RANGE = "income_range"
    GOAL = "goal"
    RISK_PROFILE = "risk_profile"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"

class MemorySystem(MemoryProvider):
    """
    Central memory authority.
    Enforces retrieval caps: MAX 4 episodic, MAX 3 semantic.
    Conflict resolution: semantic > episodic > recency
    """
    MAX_EPISODIC = 4
    MAX_SEMANTIC = 3
    
    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Episodic memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                trigger_type TEXT NOT NULL,
                event_summary TEXT NOT NULL,
                interpretation TEXT NOT NULL,
                behavioral_effect TEXT NOT NULL,
                related_category TEXT,
                confidence_score REAL DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Semantic memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                attribute_type TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.9,
                confirmed_count INTEGER DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, attribute_type)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def store_episodic(self, user_id: int, memory: Dict) -> int:
        """
        Store episodic memory.
        
        Args:
            memory: {
                'trigger_type': str (enum value),
                'event_summary': str,
                'interpretation': str,
                'behavioral_effect': str,
                'related_category': str (optional),
                'confidence_score': float (optional, default 0.8)
            }
        
        Returns:
            memory_id: int
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO episodic_memory 
            (user_id, trigger_type, event_summary, interpretation, behavioral_effect, related_category, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            memory['trigger_type'],
            memory['event_summary'],
            memory['interpretation'],
            memory['behavioral_effect'],
            memory.get('related_category'),
            memory.get('confidence_score', 0.8)
        ))
        
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"[MEMORY] Stored episodic memory {memory_id} for user {user_id}")
        return memory_id
    
    def store_semantic(self, user_id: int, memory: Dict) -> int:
        """
        Store or update semantic memory.
        If attribute exists: increment confirmed_count, update confidence.
        If new: insert.
        
        Args:
            memory: {
                'attribute_type': str (enum value),
                'value': str,
                'confidence': float (optional, default 0.9)
            }
        
        Returns:
            memory_id: int
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("""
            SELECT id, confirmed_count FROM semantic_memory
            WHERE user_id = ? AND attribute_type = ?
        """, (user_id, memory['attribute_type']))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            memory_id, count = existing
            cursor.execute("""
                UPDATE semantic_memory
                SET value = ?,
                    confidence = ?,
                    confirmed_count = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                memory['value'],
                memory.get('confidence', 0.9),
                count + 1,
                memory_id
            ))
            print(f"[MEMORY] Updated semantic memory {memory_id} (confirmed {count + 1} times)")
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO semantic_memory
                (user_id, attribute_type, value, confidence, confirmed_count)
                VALUES (?, ?, ?, ?, 1)
            """, (
                user_id,
                memory['attribute_type'],
                memory['value'],
                memory.get('confidence', 0.9)
            ))
            memory_id = cursor.lastrowid
            print(f"[MEMORY] Stored new semantic memory {memory_id}")
        
        conn.commit()
        conn.close()
        return memory_id
    
    def retrieve_context(
        self,
        user_id: int,
        query: str,
        limit: Optional[Dict] = None
    ) -> Dict:
        """
        Retrieve memory with STRICT caps.
        
        Retrieval strategy:
        - Episodic: confidence_score DESC, created_at DESC
        - Semantic: confirmed_count DESC, last_updated DESC
        
        Returns: {
            'episodic': [{...}, ...],
            'semantic': [{...}, ...],
            'total_retrieved': int
        }
        """
        limits = limit or {}
        max_episodic = limits.get('max_episodic', self.MAX_EPISODIC)
        max_semantic = limits.get('max_semantic', self.MAX_SEMANTIC)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Dict-like rows
        cursor = conn.cursor()
        
        # Retrieve episodic
        cursor.execute("""
            SELECT * FROM episodic_memory
            WHERE user_id = ?
            ORDER BY confidence_score DESC, created_at DESC
            LIMIT ?
        """, (user_id, max_episodic))
        episodic = [dict(row) for row in cursor.fetchall()]
        
        # Retrieve semantic
        cursor.execute("""
            SELECT * FROM semantic_memory
            WHERE user_id = ?
            ORDER BY confirmed_count DESC, last_updated DESC
            LIMIT ?
        """, (user_id, max_semantic))
        semantic = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        total = len(episodic) + len(semantic)
        print(f"[MEMORY] Retrieved {len(episodic)} episodic + {len(semantic)} semantic = {total} memories")
        
        return {
            'episodic': episodic,
            'semantic': semantic,
            'total_retrieved': total
        }
    
    def get_all_episodic(self, user_id: int) -> List[Dict]:
        """Debug: Get all episodic memories"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM episodic_memory WHERE user_id = ?", (user_id,))
        memories = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return memories
    
    def get_all_semantic(self, user_id: int) -> List[Dict]:
        """Debug: Get all semantic memories"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM semantic_memory WHERE user_id = ?", (user_id,))
        memories = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return memories
