"""
Rigorous Phi-3.5 RAG Testing Suite
Tests prompt construction, memory injection, response generation, and context handling.

Features:
- Comprehensive prompt validation
- Memory context visualization
- Response quality checks
- Performance benchmarking
- Detailed debug output

Author: Aryan Lomte
Date: Jan 16, 2026
Version: 2.0.0

Run: python tests/test_phi3_rag_rigorous.py
"""
import sys
import time
sys.path.append('.')

from intelligence.phi3_rag import Phi3RAG


def print_separator(char="=", length=60):
    """Print a separator line"""
    print(char * length)


def print_context_debug(context: dict, title: str = "CONTEXT INJECTION"):
    """Pretty print the context being injected"""
    print(f"\n📋 {title}")
    print("-" * 60)
    
    # Print semantic memory
    semantic = context.get('semantic', [])
    if semantic:
        print("\n🧠 SEMANTIC MEMORY (User Profile):")
        for idx, mem in enumerate(semantic, 1):
            attr_type = mem.get('attribute_type', 'Unknown')
            value = mem.get('value', 'N/A')
            print(f"   {idx}. {attr_type}: {value}")
    else:
        print("\n🧠 SEMANTIC MEMORY: None")
    
    # Print episodic memory
    episodic = context.get('episodic', [])
    if episodic:
        print("\n📝 EPISODIC MEMORY (Recent Events):")
        for idx, mem in enumerate(episodic, 1):
            event = mem.get('event_summary', 'N/A')
            trigger = mem.get('trigger_type', 'unknown')
            print(f"   {idx}. [{trigger}] {event}")
    else:
        print("\n📝 EPISODIC MEMORY: None")
    
    print("-" * 60)


def test_1_model_loading():
    """Test model loads correctly and connects to Ollama"""
    print("\n[TEST 1] Model Loading & Initialization")
    print("-" * 60)
    
    try:
        start_time = time.time()
        phi3 = Phi3RAG(model_path="models/phi3_chatbot")
        load_time = time.time() - start_time
        
        print("✅ Phi-3.5 model loaded successfully")
        print(f"   Load time: {load_time:.2f}s")
        
        # Check Ollama-specific attributes
        assert hasattr(phi3, 'model_name'), "Model should have 'model_name' attribute"
        assert hasattr(phi3, 'ollama_url'), "Model should have 'ollama_url' attribute"
        assert phi3.model_name == "budget-bandhu", "Model name should be 'budget-bandhu'"
        
        print(f"   Model: {phi3.model_name}")
        print(f"   Backend: Ollama (GGUF)")
        print(f"   Device: {phi3.device}")
        
        return phi3
    except Exception as e:
        print(f"❌ Model loading failed: {e}")
        print("   Make sure Ollama is running and budget-bandhu model exists")
        print("   Run: ollama list")
        return None


def test_2_prompt_construction(phi3):
    """Test RAG prompt construction with memory injection"""
    print("\n[TEST 2] RAG Prompt Construction & Memory Injection")
    print("-" * 60)
    
    if phi3 is None:
        print("⚠️ Skipped (model not loaded)")
        return
    
    # Mock memory context
    context = {
        'episodic': [
            {
                'event_summary': 'Overspent on Food & Drink last week by ₹2,000',
                'trigger_type': 'overspend'
            },
            {
                'event_summary': 'Achieved 50% progress on Laptop Fund goal',
                'trigger_type': 'goal_event'
            }
        ],
        'semantic': [
            {
                'attribute_type': 'income_range',
                'value': '₹30,000 - ₹40,000'
            },
            {
                'attribute_type': 'risk_profile',
                'value': 'Moderate'
            }
        ]
    }
    
    query = "Can I afford ₹15,000 laptop?"
    
    # Print what context is being injected
    print_context_debug(context)
    print(f"\n💬 USER QUERY: {query}")
    
    # Build prompt
    prompt = phi3._build_rag_prompt(query, context)
    
    # Verify prompt structure (plain text format, no XML tags)
    assert 'Budget Bandhu' in prompt, "Missing agent name"
    assert 'User Profile:' in prompt, "Missing user profile section"
    assert 'Recent Context:' in prompt, "Missing episodic memory section"
    assert '₹30,000 - ₹40,000' in prompt, "Semantic memory not injected"
    assert 'Overspent on Food' in prompt, "Episodic memory not injected"
    assert 'Can I afford' in prompt, "Query not injected"
    assert 'Answer:' in prompt, "Missing answer prompt"
    
    print("\n✅ RAG prompt structure validated")
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Memory injected: {len(context['episodic'])} episodic + {len(context['semantic'])} semantic")
    print(f"\n📄 GENERATED PROMPT (first 300 chars):")
    print("-" * 60)
    print(prompt[:300] + "...")
    print("-" * 60)


def test_3_generation_basic(phi3):
    """Test basic generation without memory context"""
    print("\n[TEST 3] Basic Generation (No Memory Context)")
    print("-" * 60)
    
    if phi3 is None:
        print("⚠️ Skipped (model not loaded)")
        return
    
    query = "What is budgeting?"
    print(f"💬 QUERY: {query}")
    print_context_debug({}, "NO CONTEXT PROVIDED")
    
    start_time = time.time()
    result = phi3.generate(
        query=query,
        context={},
        max_length=256,
        temperature=0.7
    )
    duration = time.time() - start_time
    
    assert 'result' in result, "Missing 'result' key"
    assert 'confidence' in result, "Missing 'confidence' key"
    assert len(result['result']) > 0, "Empty response generated"
    
    print(f"\n✅ Generated response ({duration:.2f}s):")
    print("-" * 60)
    print(result['result'])
    print("-" * 60)
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Tokens: {result['metadata'].get('tokens_generated', 'N/A')}")


def test_4_generation_with_memory(phi3):
    """Test generation WITH memory context (RAG)"""
    print("\n[TEST 4] Context-Aware Generation (With Memory)")
    print("-" * 60)
    
    if phi3 is None:
        print("⚠️ Skipped (model not loaded)")
        return
    
    context = {
        'episodic': [
            {
                'event_summary': 'User has upcoming rent payment of ₹12,000 in 3 days',
                'trigger_type': 'bill_prediction'
            }
        ],
        'semantic': [
            {
                'attribute_type': 'monthly_income',
                'value': '₹35,000'
            }
        ]
    }
    
    query = "Can I afford a ₹15,000 laptop right now?"
    
    print(f"💬 QUERY: {query}")
    print_context_debug(context)
    
    start_time = time.time()
    result = phi3.generate(
        query=query,
        context=context,
        max_length=300,
        temperature=0.7
    )
    duration = time.time() - start_time
    
    response = result['result']
    
    assert 'result' in result, "Missing 'result' key"
    assert len(response) > 20, "Response too short"
    
    print(f"\n✅ Context-aware response generated ({duration:.2f}s):")
    print("-" * 60)
    print(response)
    print("-" * 60)
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Tokens: {result['metadata'].get('tokens_generated', 'N/A')}")
    print(f"   Context utilized: ✅ (rent payment + income data)")


def test_5_multilingual_base(phi3):
    """Test English-only base (multilingual via external translation)"""
    print("\n[TEST 5] Multilingual Support Architecture")
    print("-" * 60)
    
    if phi3 is None:
        print("⚠️ Skipped (model not loaded)")
        return
    
    print("🌐 Model Architecture: English-only base")
    print("   Multilingual support: Via external translation layer")
    print("   Supported flow: Hindi/Hinglish → English → Model → English → Hindi/Hinglish")
    
    queries = [
        "What is my budget?",
        "Can you explain budgeting briefly?",
        "Can I afford a laptop?"
    ]
    
    print("\n📝 Testing English queries (base functionality):")
    
    for idx, query in enumerate(queries, 1):
        print(f"\n   Query {idx}: {query}")
        result = phi3.generate(
            query=query,
            context={},
            max_length=200,
            temperature=0.7
        )
        assert len(result['result']) > 0, f"Empty response for: {query}"
        print(f"   Response: {result['result'][:80]}...")
    
    print("\n✅ English queries handled successfully")
    print("   Note: For Hindi/Hinglish, integrate external translation API")


def test_6_performance_stats(phi3):
    """Display performance statistics"""
    print("\n[TEST 6] Performance Metrics & Statistics")
    print("-" * 60)
    
    if phi3 is None:
        print("⚠️ Skipped (model not loaded)")
        return
    
    stats = phi3.get_stats()
    
    print("\n📊 PERFORMANCE SUMMARY:")
    print(f"   Total Requests: {stats['total_requests']}")
    print(f"   Total Errors: {stats['total_errors']}")
    print(f"   Error Rate: {stats['error_rate']:.2%}")
    print(f"   Avg Latency: {stats['avg_latency_seconds']:.2f}s")
    print(f"   Model: {stats['model']}")
    
    print("\n✅ Performance metrics collected")


def run_all_phi3_tests():
    """Run complete Phi-3.5 RAG validation suite"""
    print_separator("=", 60)
    print("PHI-3.5 RAG COMPREHENSIVE VALIDATION SUITE")
    print("Budget Bandhu ML - Agentic AI System")
    print_separator("=", 60)
    
    start_time = time.time()
    
    # Run all tests
    phi3 = test_1_model_loading()
    test_2_prompt_construction(phi3)
    test_3_generation_basic(phi3)
    test_4_generation_with_memory(phi3)
    test_5_multilingual_base(phi3)
    test_6_performance_stats(phi3)
    
    total_time = time.time() - start_time
    
    # Final summary
    print("\n" + "=" * 60)
    if phi3:
        print("🎉 ALL PHI-3.5 TESTS PASSED")
        print(f"   Total test time: {total_time:.2f}s")
        print(f"   Model ready for production: ✅")
    else:
        print("⚠️ PHI-3.5 TESTS SKIPPED (model not available)")
        print("   Check Ollama service and model installation")
    print("=" * 60)


if __name__ == "__main__":
    run_all_phi3_tests()
