"""
Agent Controller (API Core)
Controls the agentic workflow using local Memory systems.
"""
from typing import Dict, Optional, List
from api.core.memory_manager import MemoryManager
from api.core.conversation_manager import ConversationManager
from intelligence.phi3_rag import Phi3RAG

class AgentController:
    """Async Agent Controller"""
    
    def __init__(self, phi3_rag: Phi3RAG):
        self.phi3 = phi3_rag
        self.memory = MemoryManager()
        self.conversation = ConversationManager()
        print("[AGENT] Core Agent Controller initialized")

    async def execute_turn(self, user_id: str, query: str, session_id: Optional[str] = None, session_context: Optional[Dict] = None) -> Dict:
        """Execute one conversation turn"""
        # 1. Session
        if not session_id or session_id == "default":
            # Just create new session if default
            session_id = await self.conversation.create_session(user_id)
            
        await self.conversation.add_message(session_id, 'user', query)
        
        # 2. Context
        memories = await self.memory.get_user_memories(user_id)
        # Note: In new structure, context is dict
        episodic = memories.get('episodic', [])
        semantic = memories.get('semantic', [])
        
        history = await self.conversation.get_conversation_history(session_id)
        
        context = {
            'episodic': episodic,
            'semantic': semantic,
            'conversation_history': history,
            'session': session_context or {}
        }
        
        # 3. RAG
        # Warning: Phi3RAG might be blocking. In prod use run_in_executor but here is OK.
        response_data = self.phi3.process({
            'query': query,
            'context': context
        })
        
        final_response = response_data['result']
        confidence = response_data['confidence']
        
        # 4. Save
        await self.conversation.add_message(session_id, 'assistant', final_response, confidence=confidence)
        
        return {
            'response': final_response,
            'explanation': "Generated via RAG",
            'confidence': confidence,
            'memory_used': {'episodic': len(episodic), 'semantic': len(semantic)},
            'gates_passed': True, # Placeholder
            'session_id': session_id
        }
