"""
Gating Logic - Safety & Validation
All responses must pass gates before delivery.

Author: Aryan Lomte
Date: Jan 13, 2026
"""
import logging
logger = logging.getLogger(__name__)

from enum import Enum
from typing import Dict, List

class DecisionGate(Enum):
    """Gates that responses must pass"""
    SCOPE_VALID = "scope_valid"
    SAFETY = "safety"
    EVIDENCE_BACKED = "evidence_backed"
    MEMORY_CONSISTENT = "memory_consistent"
    USER_INTENT_ALIGNED = "user_intent_aligned"

class GatingSystem:
    """
    Validates all responses before delivery.
    If any gate fails, response is modified or suppressed.
    """
    
    # Financial keywords (scope validation)
    FINANCIAL_KEYWORDS = [
        "budget", "expense", "income", "savings", "investment", "tax",
        "emi", "loan", "rent", "salary", "spending", "money", "rupee",
        "afford", "save", "spend", "earn", "₹", "rs", "inr",
        "purchase", "buy", "bought", "cost", "price", "expensive", "cheap",
        "bill", "payment", "transaction", "bank", "account", "wallet",
        "card", "credit", "debit", "cash", "worth", "value", "pc", "computer",
        "spent", "pay", "paid", "upi", "gpay", "phonepe", "paytm", "swiggy", "zomato", "amazon", "flipkart", "ola", "uber", "blinkit", "zepto"
    ]
    
    # Unsafe advice patterns
    UNSAFE_PATTERNS = [
        "guaranteed returns", "risk-free investment", "double your money",
        "get rich quick", "crypto pump", "insider trading"
    ]
    
    def __init__(self):
        pass
    
    def validate(self, response: str, memory_context: Dict, query: str) -> Dict:
        """
        Run all gates.
        
        Returns: {
            'passed': bool,
            'failed_gates': [DecisionGate],
            'modified_response': str (if needed)
        }
        """
        failed = []
        modified = response
        
        # Gate 1: Scope validity
        if not self._check_scope(query):
            failed.append(DecisionGate.SCOPE_VALID)
            modified = "I'm Bandhu, your financial assistant. I can help with budgets, expenses, savings, and investments. Could you rephrase your question?"
        
        # Gate 2: Safety
        if not self._check_safety(response):
            failed.append(DecisionGate.SAFETY)
            modified = self._sanitize_response(response)
        
        # Gate 3: Evidence backing (basic check)
        if not self._check_evidence(response, memory_context):
            failed.append(DecisionGate.EVIDENCE_BACKED)
            # Add disclaimer if making predictions without data
            if "will" in response.lower() or "predict" in response.lower():
                modified = response + "\n\n(Note: This is a general estimate based on available data.)"
        
        # Gate 4: Memory consistency
        if not self._check_memory_consistency(response, memory_context):
            failed.append(DecisionGate.MEMORY_CONSISTENT)
            # Log inconsistency (don't modify response yet)
        
        return {
            'passed': len(failed) == 0,
            'failed_gates': [gate.value for gate in failed],
            'modified_response': modified
        }
    
    def _check_scope(self, query: str) -> bool:
        """
        Is query within financial domain?
        Returns True if at least one financial keyword present.
        """
        query_lower = query.lower()
        passed = any(kw in query_lower for kw in self.FINANCIAL_KEYWORDS)
        logger.info(f"[GATING] Scope check for '{query}': {'PASSED' if passed else 'FAILED'}")
        return passed
    
    def _check_safety(self, response: str) -> bool:
        """
        Check for unsafe financial advice patterns.
        Returns False if any unsafe pattern detected.
        """
        response_lower = response.lower()
        return not any(pattern in response_lower for pattern in self.UNSAFE_PATTERNS)
    
    def _sanitize_response(self, response: str) -> str:
        """Remove or modify unsafe advice"""
        # Placeholder: In production, use more sophisticated NLP
        return "I cannot provide that type of investment advice. Please consult a certified financial advisor for high-risk strategies."
    
    def _check_evidence(self, response: str, memory: Dict) -> bool:
        """
        Basic check: Does response reference retrieved context?
        Production: Use NLI or semantic similarity.
        """
        # If we retrieved memories, response should be grounded
        if memory.get('total_retrieved', 0) > 0:
            # Placeholder: Always pass for now
            return True
        return True
    
    def _check_memory_consistency(self, response: str, memory: Dict) -> bool:
        """
        Does response contradict semantic memory?
        Production: Use contradiction detection model.
        """
        # Placeholder: Always pass for now
        return True
