"""
Isolation Forest Anomaly Detection
Wrapper for your trained model.

Author: Tanuj
Date: Jan 13, 2026
"""
import joblib
import numpy as np
from typing import List, Dict
import json
import os

from intelligence.base import IntelligenceComponent


class AnomalyDetector(IntelligenceComponent):
    """
    Flags unusual transactions using your Isolation Forest model.
    Uses 3 features: [amount, category_id, z_score]
    Z-score = how unusual is this amount FOR THIS CATEGORY
    """
    
    def __init__(self, model_path: str, category_map_path: str):
        """
        Args:
            model_path: Path to your trained Isolation Forest
            category_map_path: Category encoding map
        """
        print(f"[ANOMALY] Loading Isolation Forest from {model_path}")
        
        # Load model
        self.model = joblib.load(model_path)
        
        # Load category map
        with open(category_map_path, 'r') as f:
            self.category_map = json.load(f)
        
        print("[ANOMALY] Model loaded successfully (2-feature mode: amount, category)")
    
    def process(self, input_data: Dict) -> Dict:
        """
        Detect anomalies in batch.
        
        Input:
            {'transactions': [...]}
        
        Output:
            {
                'result': [...],  # Transactions with anomaly flags
                'stats': {...}
            }
        """
        transactions = input_data['transactions']
        flagged = self.detect_batch(transactions)
        stats = self._compute_stats(flagged)
        
        return {
            'result': flagged,
            'stats': stats
        }
    
    def detect_batch(self, transactions: List[Dict]) -> List[Dict]:
        """
        Returns transactions with anomaly flags.
        Uses PURE Isolation Forest with 3 features.
        """
        if not transactions:
            return []
        
        features = self._extract_features(transactions)
        predictions = self.model.predict(features)
        scores = self.model.decision_function(features)
        
        results = []
        for i, txn in enumerate(transactions):
            results.append({
                **txn,
                'is_anomaly': bool(predictions[i] == -1),
                'anomaly_score': float(scores[i]),
                'severity': self._compute_severity(scores[i])
            })
        
        return results
    
    def _get_zscore(self, amount: float, category: str) -> float:
        """Calculate z-score (kept for compatibility but not used in 2-feature mode)"""
        stats = self.category_stats.get(category, {'mean': 1500, 'std': 1000})
        mean = stats.get('mean', 1500)
        std = stats.get('std', 1000)
        if std == 0:
            std = 500
        return (amount - mean) / std
    
    def _extract_features(self, transactions: List[Dict]) -> np.ndarray:
        """
        Extract features: [amount, category_id]
        Model trained on REALISTIC Indian transaction data.
        """
        features = []
        
        for txn in transactions:
            amount = float(txn.get('amount', 0))
            category = txn.get('category', 'Other')
            category_encoded = self.category_map.get(category, self.category_map.get("Other", 8))
            
            features.append([amount, category_encoded])
        
        return np.array(features)
    
    def _compute_severity(self, score: float) -> str:
        """Convert anomaly score to severity"""
        if score < -0.1:
            return "high"
        elif score < 0:
            return "medium"
        else:
            return "low"
    
    def _compute_stats(self, flagged: List[Dict]) -> Dict:
        """Compute anomaly statistics"""
        total = len(flagged)
        anomalies = len([t for t in flagged if t['is_anomaly']])
        
        return {
            'total': total,
            'anomalies': anomalies,
            'anomaly_rate': anomalies / total if total > 0 else 0,
            'high_severity': len([t for t in flagged if t['severity'] == 'high'])
        }
