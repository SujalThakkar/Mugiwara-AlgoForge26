"""
Agent Controller - The Sovereign Authority (Async MongoDB Edition)
Controls the entire agentic lifecycle with multi-turn conversation tracking.

Features:
- 9-step agentic workflow
- Async IO for high performance
- MongoDB integration
- Mobile number based identity

Author: Aryan Lomte
Date: Jan 16, 2026
Version: 2.1.0 (Async)
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid

from memory.memory_manager import MemoryManager
from memory.conversation_manager import ConversationManager
from intelligence.phi3_rag import Phi3RAG
from core.gating import GatingSystem


class AgentController:
    """
    Async Agent controller.
    """
    
    def __init__(
        self,
        phi3_rag: Phi3RAG,
        memory_manager: MemoryManager,
        conversation_manager: ConversationManager,
        gating_system: Optional[GatingSystem] = None
    ):
        self.phi3 = phi3_rag
        self.memory = memory_manager
        self.conversation = conversation_manager
        self.gating = gating_system or GatingSystem()
        
        self.stats = {
            'total_turns': 0,
            'successful_turns': 0,
            'failed_gates': 0,
            'memories_used': 0
        }
        print("[AGENT] Async Agent Controller initialized")
    
    async def execute_turn(
        self,
        user_id: str,  # Mobile Number
        query: str,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Execute one conversation turn (Async).
        """
        self.stats['total_turns'] += 1
        print(f"\n[AGENT] ===== NEW TURN for {user_id} =====")
        
        # STEP 1: Normalize
        normalized_query = " ".join(query.split()).strip()
        
        # STEP 2: Session
        if not session_id:
            session_id = await self.conversation.create_session(user_id)
            print(f"[AGENT] Created session {session_id}")
        
        # Log user message
        await self.conversation.add_message(session_id, 'user', query)
        
        # STEP 3: Memory Retrieval
        memory_context = await self.memory.get_user_memories(user_id)
        episodic_count = len(memory_context.get('episodic', []))
        semantic_count = len(memory_context.get('semantic', []))
        total_memories = episodic_count + semantic_count
        self.stats['memories_used'] += total_memories
        
        # STEP 4: History Retrieval
        conversation_history = await self.conversation.get_conversation_history(
            session_id, limit=6
        )
        
        # STEP 5: Context
        reconstructed_context = {
            'query': normalized_query,
            'episodic': memory_context.get('episodic', []),
            'semantic': memory_context.get('semantic', []),
            'conversation_history': conversation_history
        }
        
        # STEP 6: Reasoning (Phi-3 is synchronous CPU bound or HTTP bound, but we treat as is)
        # Verify: Phi3RAG.process calls requests.post which is blocking.
        # Ideally we should make Phi3RAG async too, but for now blocking call inside async def is acceptable 
        # for this scale, or run in threadpool. Given it's a microservice, let's keep it simple.
        proposed_response = self.phi3.process({
            'query': normalized_query,
            'context': reconstructed_context,
            'max_length': 400
        })
        
        # STEP 7: Gating
        gate_result = self.gating.validate(
            response=proposed_response['result'],
            memory_context=memory_context,
            query=normalized_query
        )
        
        final_response = gate_result['modified_response'] if not gate_result['passed'] else proposed_response['result']
        if not gate_result['passed']:
            self.stats['failed_gates'] += 1
            
        # STEP 8: Delivery & Storage
        response_obj = {
            'response': final_response,
            'session_id': session_id,
            'confidence': proposed_response['confidence'],
            'gates_passed': gate_result['passed']
        }
        
        await self.conversation.add_message(
            session_id,
            'assistant',
            final_response,
            confidence=proposed_response['confidence']
        )
        
        # STEP 9: Learning
        await self._evaluate_learning(user_id, normalized_query, final_response, gate_result['passed'])
        
        return response_obj

    async def _evaluate_learning(self, user_id: str, query: str, response: str, gates_passed: bool):
        """Async learning evaluation"""
        if not gates_passed:
            # Maybe store a "failure" memory?
            pass
        
    def get_stats(self) -> Dict:
        return self.stats
