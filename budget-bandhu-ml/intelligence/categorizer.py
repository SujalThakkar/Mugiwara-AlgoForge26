"""
Transaction Categorization Engine
Fast path: Rules (80% accuracy)
Ambiguous path: Your Phi-3.5 Categorizer (20%)
Manual override → feeds episodic memory

Author: Tanuj
Date: Jan 13, 2026
"""
import re
import torch
from typing import List, Dict, Optional
import json

from intelligence.base import IntelligenceComponent


class TransactionCategorizer(IntelligenceComponent):
    """
    Production-grade categorization pipeline.
    Categories: 15 Indian financial categories.
    """
    
    CATEGORIES = [
        "Food & Drink", "Rent", "Utilities", "Shopping", "Entertainment",
        "Travel", "Health & Fitness", "Investment", "Salary", "EMI",
        "Insurance", "Education", "Groceries", "Personal Care", "Other"
    ]
    
    # Rule-based patterns (Indian context) - EXPANDED
    RULES = {
        "Food & Drink": [
            r'swiggy|zomato|restaurant|cafe|food|dining|coffee|mcdonalds|dominos',
            r'food delivery|restaurant.*pay|dining out|pizza|burger|starbucks',
            r'chai|tea|snacks|breakfast|lunch|dinner|uber eats|blinkit food'
        ],
        "Rent": [r'rent|housing|pg rent|hostel fee|rent payment|kumar'],
        "Utilities": [
            r'electricity|water|broadband|jio|airtel|vi|mobile recharge|gas bill',
            r'tata power|bses|phone bill|internet|wifi|recharge|bill payment'
        ],
        "Shopping": [
            r'amazon|flipkart|myntra|ajio|meesho|shopping|electronics',
            r'prime renewal|books|purchase|order|buy|pc|gaming|computer',
            r'clothing|apparel|zara|h&m|pantaloons|lifestyle'
        ],
        "Entertainment": [
            r'netflix|spotify|prime video|movie|cinema|hotstar|zee5',
            r'pvr|inox|youtube|gaming|tickets|subscription'
        ],
        "Travel": [
            r'uber|ola|rapido|train|flight|irctc|bus|metro|ride|airport',
            r'petrol|diesel|fuel|indian oil|hp|bharat petroleum|bike'
        ],
        "Salary": [r'salary|credited|income|payroll|reimbursement|freelance'],
        "EMI": [r'emi|loan|credit card|repayment'],
        "Investment": [r'mutual fund|sip|ppf|fd|rd|stock|groww|zerodha|investment'],
        "Insurance": [r'insurance|lic|health insurance|term plan'],
        "Education": [r'fees|tuition|course|education|books'],
        "Groceries": [
            r'groceries|vegetables|fruits|grocery|bigbasket|blinkit|zepto',
            r'reliance fresh|dmart|more|supermarket|provisions'
        ],
        "Health & Fitness": [
            r'gym|fitness|cult|medical|pharmacy|hospital|doctor|apollo',
            r'medicine|health|workout|yoga|membership'
        ],
        "Personal Care": [
            r'salon|barber|parlour|spa|makeup|cosmetic|beauty|skincare'
        ]
    }
    
    def __init__(self, phi3_model_path: Optional[str] = None):
        """
        Args:
            phi3_model_path: Path to your Phi-3.5 categorizer model
        """
        self.phi3_model_path = phi3_model_path
        
        # Load Phi-3.5 categorizer if available
        self.phi3_categorizer = None
        if phi3_model_path:
            self._load_phi3_categorizer(phi3_model_path)
    
    def _load_phi3_categorizer(self, model_path: str):
        """Load your fine-tuned Phi-3.5 categorizer"""
        print(f"[CATEGORIZER] Initializing Phi-3.5 fallback (Ollama mode)")
        # We use Ollama API for categorization fallback
        import requests
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                self.phi3_categorizer = True
                print("[CATEGORIZER] Phi-3.5 fallback READY via Ollama")
            else:
                print("[CATEGORIZER] Ollama returned error, Phi-3 fallback DISABLED")
        except Exception as e:
            print(f"[CATEGORIZER] Ollama NOT FOUND, Phi-3 fallback DISABLED: {e}")
    
    def process(self, input_data: Dict) -> Dict:
        """
        Categorize batch of transactions.
        
        Input:
            {
                'transactions': [
                    {'date': '2026-01-01', 'amount': 150.0, 'description': 'Swiggy order #123'},
                    ...
                ]
            }
        
        Output:
            {
                'result': [{'transaction': {...}, 'category': 'Food & Drink', 'method': 'rule'}, ...],
                'stats': {'total': 45, 'rule_based': 36, 'phi3': 9, 'unknown': 0}
            }
        """
        transactions = input_data['transactions']
        categorized = self.categorize_batch(transactions)
        stats = self._compute_stats(categorized)
        
        return {
            'result': categorized,
            'stats': stats
        }
    
    def categorize_batch(self, transactions: List[Dict]) -> List[Dict]:
        """
        Production categorization pipeline.
        """
        results = []
        
        for txn in transactions:
            category = self._rule_based_categorize(txn.get('description', ''))
            
            # If rule-based fails → use Phi-3.5
            if category == "Other" and self.phi3_categorizer:
                category = self._phi3_categorize(txn)
            
            results.append({
                **txn,
                'category': category,
                'method': 'rule' if category != "Other" or not self.phi3_categorizer else 'phi3',
                'confidence': self._get_confidence(category, txn)
            })
        
        return results
    
    def _rule_based_categorize(self, description: str) -> str:
        """Fast rule-based categorization (80% coverage)"""
        if not description:
            return "Other"
        
        desc_lower = description.lower()
        
        for category, patterns in self.RULES.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower):
                    return category
        
        return "Other"
    
    def _phi3_categorize(self, txn: Dict) -> str:
        """Phi-3.5 categorization for ambiguous cases via Ollama"""
        import requests
        
        prompt = f"""Categorize this Indian transaction into exactly one of these categories:
{", ".join(self.CATEGORIES)}

Transaction: {txn.get('description')}
Amount: ₹{txn.get('amount')}

Respond with ONLY the category name."""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "budget-bandhu",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0}
                },
                timeout=5
            )
            if response.status_code == 200:
                result = response.json().get('response', '').strip()
                # Validate result is in CATEGORIES
                for cat in self.CATEGORIES:
                    if cat.lower() in result.lower():
                        return cat
            return "Other"
        except Exception as e:
            print(f"[CATEGORIZER] Phi-3 Error: {e}")
            return "Other"
    
    def _get_confidence(self, category: str, txn: Dict) -> float:
        """Assign confidence score"""
        amount = txn.get('amount', 0)
        desc_len = len(txn.get('description', ''))
        
        # Rule-based: high confidence
        if category != "Other":
            return 0.95
        
        # Phi-3.5: medium confidence
        if txn.get('method') == 'phi3':
            return 0.85
        
        # Unknown: low confidence
        return 0.6
    
    def _compute_stats(self, categorized: List[Dict]) -> Dict:
        """Compute categorization statistics"""
        total = len(categorized)
        rule_based = len([t for t in categorized if t.get('method') == 'rule'])
        phi3 = len([t for t in categorized if t.get('method') == 'phi3'])
        unknown = len([t for t in categorized if t.get('category') == 'Other'])
        
        return {
            'total': total,
            'rule_based': rule_based,
            'phi3': phi3,
            'unknown': unknown,
            'accuracy_estimate': (rule_based + phi3) / total if total > 0 else 0
        }
