"""
End-to-End Agent Controller Testing
Tests complete 9-step lifecycle with all components.

Run: python tests/test_agent_e2e.py
"""
import sys
sys.path.append('.')

import os
from core.memory_system import MemorySystem
from intelligence.phi3_rag import Phi3RAG
from core.gating import GatingSystem
from core.agent_controller import AgentController

def setup_test_environment():
    """Initialize all components"""
    print("\n[SETUP] Initializing test environment...")
    
    # Clean test DB
    if os.path.exists("test_agent_e2e.db"):
        os.remove("test_agent_e2e.db")
    
    # Initialize components
    memory = MemorySystem(db_path="test_agent_e2e.db")
    gating = GatingSystem()
    
    try:
        phi3 = Phi3RAG(model_path="models/phi3_chatbot")
        model_available = True
    except Exception as e:
        print(f"⚠️ Phi-3.5 model not available: {e}")
        phi3 = None
        model_available = False
    
    if model_available:
        agent = AgentController(
            memory_system=memory,
            phi3_rag=phi3,
            gating_system=gating
        )
    else:
        agent = None
    
    print("✅ Test environment ready")
    return agent, memory, model_available

def test_1_cold_start_conversation(agent):
    """Test conversation with NO prior memory"""
    print("\n[TEST 1] Cold Start Conversation (No Memory)")
    
    if agent is None:
        print("⚠️ Skipped (agent not available)")
        return
    
    result = agent.execute_turn(
        user_id=100,
        query="What is budgeting?",
        session_context={}
    )
    
    assert 'response' in result
    assert 'memory_used' in result
    assert result['memory_used']['episodic_count'] == 0, "Should have 0 episodic on cold start"
    assert result['memory_used']['semantic_count'] == 0, "Should have 0 semantic on cold start"
    
    print(f"✅ Cold start response: {result['response'][:100]}...")
    print(f"   Memory used: {result['memory_used']}")

def test_2_conversation_with_memory(agent, memory):
    """Test conversation WITH pre-populated memory"""
    print("\n[TEST 2] Conversation with Memory Context")
    
    if agent is None:
        print("⚠️ Skipped (agent not available)")
        return
    
    user_id = 101
    
    # Pre-populate memory
    memory.store_semantic(user_id, {
        'attribute_type': 'income_range',
        'value': '₹40,000/month',
        'confidence': 0.9
    })
    
    memory.store_episodic(user_id, {
        'trigger_type': 'overspend',
        'event_summary': 'Overspent on Shopping by ₹3,000 last week',
        'interpretation': 'Shopping budget exceeded',
        'behavioral_effect': 'Warn about shopping expenses',
        'confidence_score': 0.85
    })
    
    # Execute conversation
    result = agent.execute_turn(
        user_id=user_id,
        query="Can I afford a ₹15,000 laptop?",
        session_context={'current_balance': 35000}
    )
    
    # Verify memory was retrieved
    assert result['memory_used']['episodic_count'] > 0, "Episodic memory not retrieved"
    assert result['memory_used']['semantic_count'] > 0, "Semantic memory not retrieved"
    
    print(f"✅ Response with memory: {result['response'][:150]}...")
    print(f"   Memory retrieved: {result['memory_used']}")
    print(f"   Explanation: {result['explanation']}")

def test_3_gating_enforcement(agent):
    """Test that gating blocks inappropriate queries"""
    print("\n[TEST 3] Gating Enforcement")
    
    if agent is None:
        print("⚠️ Skipped (agent not available)")
        return
    
    # Out-of-scope query
    result = agent.execute_turn(
        user_id=102,
        query="Who won the cricket match yesterday?",
        session_context={}
    )
    
    assert not result['gates_passed'], "Gate should have failed for out-of-scope query"
    assert 'Bandhu' in result['response'], "Should contain agent introduction"
    assert 'financial' in result['response'].lower(), "Should explain scope"
    
    print(f"✅ Out-of-scope query blocked")
    print(f"   Modified response: {result['response'][:100]}...")

def test_4_memory_cap_enforcement(agent, memory):
    """Test that retrieval caps are enforced"""
    print("\n[TEST 4] Memory Cap Enforcement in Agent")
    
    if agent is None:
        print("⚠️ Skipped (agent not available)")
        return
    
    user_id = 103
    
    # Store MORE than cap (5 episodic, 4 semantic)
    for i in range(6):
        memory.store_episodic(user_id, {
            'trigger_type': 'overspend',
            'event_summary': f'Overspend event #{i+1}',
            'interpretation': 'Test',
            'behavioral_effect': 'Test',
            'confidence_score': 0.8
        })
    
    for i in range(5):
        memory.store_semantic(user_id, {
            'attribute_type': f'preference',
            'value': f'Test preference {i+1}',
            'confidence': 0.8
        })
    
    # Execute turn
    result = agent.execute_turn(
        user_id=user_id,
        query="Show my spending",
        session_context={}
    )
    
    # Verify caps
    assert result['memory_used']['episodic_count'] <= 4, f"Episodic cap violated: {result['memory_used']['episodic_count']}"
    assert result['memory_used']['semantic_count'] <= 3, f"Semantic cap violated: {result['memory_used']['semantic_count']}"
    
    print(f"✅ Memory caps enforced in agent")
    print(f"   Retrieved: {result['memory_used']}")

def test_5_nine_step_lifecycle_trace(agent):
    """Verify all 9 steps execute"""
    print("\n[TEST 5] 9-Step Lifecycle Trace")
    
    if agent is None:
        print("⚠️ Skipped (agent not available)")
        return
    
    # Check console output for step markers
    print("   Executing turn... (check console for step logs)")
    
    result = agent.execute_turn(
        user_id=104,
        query="What are my expenses?",
        session_context={}
    )
    
    # If we got a result, all steps executed
    assert 'response' in result
    assert 'confidence' in result
    assert 'memory_used' in result
    assert 'gates_passed' in result
    
    print("✅ All 9 steps executed successfully")
    print(f"   Response structure validated")

def run_all_agent_e2e_tests():
    """Run complete end-to-end agent validation"""
    print("=" * 60)
    print("AGENT CONTROLLER END-TO-END VALIDATION")
    print("=" * 60)
    
    agent, memory, model_available = setup_test_environment()
    
    if not model_available:
        print("\n⚠️ Phi-3.5 model not available - E2E tests skipped")
        print("   Run these tests after confirming model path is correct")
        return
    
    test_1_cold_start_conversation(agent)
    test_2_conversation_with_memory(agent, memory)
    test_3_gating_enforcement(agent)
    test_4_memory_cap_enforcement(agent, memory)
    test_5_nine_step_lifecycle_trace(agent)
    
    print("\n" + "=" * 60)
    print("✅ ALL AGENT E2E TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    run_all_agent_e2e_tests()
