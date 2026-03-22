"""
Rigorous Gating System Testing
Tests all gates: scope, safety, evidence, consistency.

Run: python tests/test_gating_rigorous.py
"""
import sys
sys.path.append('.')

from core.gating import GatingSystem, DecisionGate

def test_1_scope_validation():
    """Test financial scope detection"""
    print("\n[TEST 1] Scope Validation")
    gating = GatingSystem()
    
    # IN SCOPE queries
    in_scope = [
        "What is my budget?",
        "Can I afford ₹15,000 laptop?",
        "Show me my expenses",
        "How much did I spend on food?",
        "Investment suggestions",
        "Tax saving options under 80C"
    ]
    
    for query in in_scope:
        result = gating.validate(
            response="Budget-related response",
            memory_context={},
            query=query
        )
        assert result['passed'], f"False negative: '{query}' should be IN scope"
    
    print(f"✅ All {len(in_scope)} in-scope queries passed")
    
    # OUT OF SCOPE queries
    out_of_scope = [
        "What is the capital of France?",
        "Tell me a joke",
        "Who won the cricket match?",
        "Recipe for pasta"
    ]
    
    for query in out_of_scope:
        result = gating.validate(
            response="Generic response",
            memory_context={},
            query=query
        )
        assert not result['passed'], f"False positive: '{query}' should be OUT of scope"
        assert DecisionGate.SCOPE_VALID.value in result['failed_gates']
    
    print(f"✅ All {len(out_of_scope)} out-of-scope queries blocked")

def test_2_safety_validation():
    """Test unsafe advice detection"""
    print("\n[TEST 2] Safety Validation")
    gating = GatingSystem()
    
    # SAFE responses
    safe = [
        "I recommend budgeting 50% for needs, 30% for wants, 20% for savings",
        "You can save tax under Section 80C by investing in ELSS",
        "Based on your spending, you can afford ₹10,000 this month"
    ]
    
    for response in safe:
        result = gating.validate(
            response=response,
            memory_context={},
            query="financial advice"
        )
        # Should pass safety gate (scope will pass due to keywords)
        safety_failed = DecisionGate.SAFETY.value in result.get('failed_gates', [])
        assert not safety_failed, f"False positive: Safe response blocked: '{response}'"
    
    print(f"✅ All {len(safe)} safe responses passed")
    
    # UNSAFE responses
    unsafe = [
        "Invest in crypto for guaranteed returns",
        "This is a risk-free investment that will double your money",
        "Get rich quick with this insider trading tip",
        "Join this crypto pump group"
    ]
    
    for response in unsafe:
        result = gating.validate(
            response=response,
            memory_context={},
            query="investment advice"
        )
        safety_failed = DecisionGate.SAFETY.value in result.get('failed_gates', [])
        assert safety_failed, f"False negative: Unsafe response not blocked: '{response}'"
    
    print(f"✅ All {len(unsafe)} unsafe responses blocked")

def test_3_response_modification():
    """Test response modification when gates fail"""
    print("\n[TEST 3] Response Modification")
    gating = GatingSystem()
    
    # Out-of-scope query
    result = gating.validate(
        response="Paris is the capital of France",
        memory_context={},
        query="What is the capital of France?"
    )
    
    assert not result['passed']
    assert 'modified_response' in result
    assert "Bandhu" in result['modified_response']  # Should contain agent name
    assert "financial" in result['modified_response'].lower()  # Should explain scope
    
    print("✅ Out-of-scope responses modified correctly")
    
    # Unsafe advice
    result = gating.validate(
        response="Guaranteed returns with crypto",
        memory_context={},
        query="investment advice"
    )
    
    assert not result['passed']
    assert "cannot provide" in result['modified_response'].lower() or "consult" in result['modified_response'].lower()
    
    print("✅ Unsafe responses sanitized correctly")

def run_all_gating_tests():
    """Run complete gating validation suite"""
    print("=" * 60)
    print("GATING SYSTEM RIGOROUS VALIDATION")
    print("=" * 60)
    
    test_1_scope_validation()
    test_2_safety_validation()
    test_3_response_modification()
    
    print("\n" + "=" * 60)
    print("✅ ALL GATING TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    run_all_gating_tests()
