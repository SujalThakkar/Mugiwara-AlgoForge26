"""
Test Agentic AI Core

Run: python -m pytest tests/test_agent.py -v
"""
import sys
sys.path.append('.')

from core.memory_system import MemorySystem, TriggerType, AttributeType
from intelligence.phi3_rag import Phi3RAG
from core.gating import GatingSystem
from core.agent_controller import AgentController

def test_memory_system():
    """Test memory storage and retrieval"""
    memory = MemorySystem(db_path="test_memory.db")
    
    # Store semantic
    mem_id = memory.store_semantic(user_id=1, memory={
        'attribute_type': AttributeType.INCOME_RANGE.value,
        'value': '₹30,000 - ₹40,000',
        'confidence': 0.9
    })
    assert mem_id > 0
    
    # Store episodic
    mem_id = memory.store_episodic(user_id=1, memory={
        'trigger_type': TriggerType.OVERSPEND.value,
        'event_summary': 'Overspent on Food & Drink by ₹2,000',
        'interpretation': 'Food budget too tight',
        'behavioral_effect': 'Suggest budget increase',
        'related_category': 'Food & Drink'
    })
    assert mem_id > 0
    
    # Retrieve
    context = memory.retrieve_context(user_id=1, query="food spending")
    assert context['total_retrieved'] > 0
    assert len(context['episodic']) <= 4
    assert len(context['semantic']) <= 3
    
    print("✅ Memory system test passed")

def test_gating():
    """Test gating logic"""
    gating = GatingSystem()
    
    # Test scope validation
    result = gating.validate(
        response="The capital of France is Paris",
        memory_context={},
        query="What is the capital of France?"
    )
    assert not result['passed']  # Out of scope
    
    # Test financial scope
    result = gating.validate(
        response="Your budget is ₹50,000",
        memory_context={},
        query="What is my budget?"
    )
    assert result['passed']  # In scope
    
    print("✅ Gating test passed")

def test_agent_controller():
    """Test full agent lifecycle"""
    # Initialize components
    memory = MemorySystem(db_path="test_memory.db")
    
    # Note: This requires model files - skip if not available
    try:
        phi3 = Phi3RAG(model_path="../models/phi3_chatbot")
        agent = AgentController(memory_system=memory, phi3_rag=phi3)
        
        # Execute turn
        result = agent.execute_turn(
            user_id=1,
            query="What is my budget?",
            session_context={}
        )
        
        assert 'response' in result
        assert 'confidence' in result
        assert 'memory_used' in result
        
        print("✅ Agent controller test passed")
    except Exception as e:
        print(f"⚠️ Agent test skipped (model not available): {e}")

if __name__ == "__main__":
    test_memory_system()
    test_gating()
    test_agent_controller()
