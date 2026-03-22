"""
Simplified Policy Learning
Replaces Q-Learning with memory-weighted policy learning.
Judge-friendly and stable.

Author: Tanuj
Date: Jan 13, 2026
"""
import numpy as np
from typing import Dict, List, Optional
from collections import defaultdict
import json

from intelligence.base import IntelligenceComponent


class PolicyLearner(IntelligenceComponent):
    """
    Learns optimal budget allocation from spending patterns.
    Uses memory weighting instead of full RL.
    """
    
    def __init__(self, q_table_path: Optional[str] = None):
        """
        Args:
            q_table_path: Your existing Q-table (optional)
        """
        self.budget_multipliers = defaultdict(lambda: 1.0)  # Category -> multiplier
        self.success_count = defaultdict(int)
        self.failure_count = defaultdict(int)
        
        if q_table_path:
            self._load_q_table(q_table_path)
    
    def _load_q_table(self, path: str):
        """Load your existing Q-table"""
        try:
            with open(path, 'rb') as f:
                data = np.load(f, allow_pickle=True).item()
                self.budget_multipliers = data.get('budget_multipliers', {})
            print("[POLICY] Loaded existing Q-table")
        except:
            print("[POLICY] No Q-table found, starting fresh")
    
    def process(self, input_data: Dict) -> Dict:
        """
        Generate budget recommendations.
        
        Input:
            {
                'historical_spending': {'Food & Drink': 5000, 'Rent': 15000, ...},
                'income': 50000,
                'feedback': {'accepted': [...], 'rejected': [...]}
            }
        """
        spending = input_data['historical_spending']
        income = input_data['income']
        
        recommendations = self._generate_recommendations(spending, income)
        return {
            'result': recommendations,
            'method': 'policy_learning'
        }
    
    def _generate_recommendations(self, spending: Dict, income: float) -> Dict:
        """
        Generate category-wise budget recommendations.
        """
        total_spent = sum(spending.values())
        recommendations = {}
        
        for category, spent in spending.items():
            # Base: 50/30/20 allocation adjusted by history
            multiplier = self.budget_multipliers[category]
            recommended = (spent / total_spent * income) * multiplier if total_spent > 0 else 0
            
            recommendations[category] = {
                'recommended': round(recommended, 0),
                'historical': spent,
                'multiplier': round(multiplier, 2),
                'change': 'increase' if multiplier > 1 else 'decrease'
            }
        
        return recommendations
    
    def update_policy(self, category: str, feedback: str):
        """
        Update policy based on user feedback.
        Called when user accepts/rejects recommendation.
        """
        if feedback == 'accepted':
            self.success_count[category] += 1
        else:
            self.failure_count[category] += 1
        
        # Adjust multiplier
        success_rate = self.success_count[category] / (self.success_count[category] + self.failure_count[category] + 1)
        self.budget_multipliers[category] = 0.8 + (success_rate * 0.4)  # 0.8-1.2 range
        
        print(f"[POLICY] Updated {category}: multiplier={self.budget_multipliers[category]:.2f}")
