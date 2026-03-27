"""
Per-User Adaptive Anomaly Detection using Isolation Forest.
Each user gets their OWN model trained on their transaction history.
Models retrain periodically as more data comes in.

Author: Tanuj
Date: Jan 16, 2026
"""
import joblib
import numpy as np
from typing import List, Dict, Optional
import json
import os
from pathlib import Path
from sklearn.ensemble import IsolationForest

from intelligence.base import IntelligenceComponent


class UserAnomalyDetector(IntelligenceComponent):
    """
    Per-user adaptive anomaly detection.
    
    How it works:
    1. First 30 transactions: Learning phase (no anomaly detection)
    2. After 30+ transactions: Train user-specific Isolation Forest
    3. Retrain every 50 new transactions
    
    Benefits:
    - Rich person's ₹50k shopping = NORMAL (for them)
    - Poor person's ₹5k shopping = ANOMALY (for them)
    - Adapts as income changes over time
    """
    
    MIN_TRANSACTIONS_FOR_TRAINING = 30
    RETRAIN_INTERVAL = 50  # Retrain after every N new transactions
    
    def __init__(self, models_dir: str = "models/user_anomaly", category_map_path: str = None):
        """
        Args:
            models_dir: Directory to store per-user models
            category_map_path: Path to category encoding map
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Load category map
        if category_map_path and os.path.exists(category_map_path):
            with open(category_map_path, 'r') as f:
                self.category_map = json.load(f)
        else:
            self.category_map = self._default_category_map()
        
        # Cache for loaded user models
        self.user_models: Dict[str, IsolationForest] = {}
        self.user_stats: Dict[str, dict] = {}
        
        print("[USER_ANOMALY] Per-user adaptive anomaly detector initialized")
    
    def _default_category_map(self) -> dict:
        return {
            "Bills & Utilities": 0, "Utilities": 0,
            "Education": 1, "Entertainment": 2,
            "Food & Dining": 3, "Food & Drink": 3,
            "Groceries": 5, "Healthcare": 6, "Health & Fitness": 6,
            "Investments": 7, "Investment": 7, "Other": 8,
            "Rent": 10, "Salary": 11, "Shopping": 12,
            "Travel": 14
        }
    
    def process(self, input_data: Dict) -> Dict:
        """
        Detect anomalies for a specific user.
        
        Input:
            {
                'user_id': 'abc123',
                'transactions': [...],
                'user_history': [...]  # Optional: all user's past transactions
            }
        """
        user_id = input_data.get('user_id', 'default')
        transactions = input_data['transactions']
        user_history = input_data.get('user_history', [])
        
        # Check if user has enough history for anomaly detection
        total_history = len(user_history)
        
        if total_history < self.MIN_TRANSACTIONS_FOR_TRAINING:
            # Learning phase - mark all as normal, but record data
            print(f"[USER_ANOMALY] User {user_id[:8]}... in learning phase ({total_history}/{self.MIN_TRANSACTIONS_FOR_TRAINING})")
            flagged = self._mark_all_normal(transactions, learning_phase=True)
        else:
            # Get or train user model
            model = self._get_or_train_user_model(user_id, user_history)
            flagged = self._detect_with_model(model, transactions)
            
            # Check if retrain needed
            self._check_retrain(user_id, user_history)
        
        stats = self._compute_stats(flagged)
        
        return {
            'result': flagged,
            'stats': stats,
            'user_learning_phase': total_history < self.MIN_TRANSACTIONS_FOR_TRAINING
        }
    
    def _get_or_train_user_model(self, user_id: str, history: List[Dict]) -> IsolationForest:
        """Get cached model or train new one"""
        
        # Check cache first
        if user_id in self.user_models:
            return self.user_models[user_id]
        
        # Check if saved model exists
        model_path = self.models_dir / f"{user_id}.pkl"
        if model_path.exists():
            model = joblib.load(model_path)
            self.user_models[user_id] = model
            print(f"[USER_ANOMALY] Loaded saved model for user {user_id[:8]}...")
            return model
        
        # Train new model
        model = self._train_user_model(user_id, history)
        return model
    
    def _train_user_model(self, user_id: str, history: List[Dict]) -> IsolationForest:
        """Train a new Isolation Forest for this user"""
        print(f"[USER_ANOMALY] Training model for user {user_id[:8]}... ({len(history)} transactions)")
        
        # Extract features from history
        X = self._extract_features(history)
        
        # Train model
        # contamination=0.05 means ~5% of user's own transactions are outliers
        model = IsolationForest(
            n_estimators=150,
            contamination=0.05,
            random_state=42
        )
        model.fit(X)
        
        # Cache and save
        self.user_models[user_id] = model
        model_path = self.models_dir / f"{user_id}.pkl"
        joblib.dump(model, model_path)
        
        # Save user stats
        self.user_stats[user_id] = {
            'transactions_trained': len(history),
            'last_trained': str(np.datetime64('now'))
        }
        
        print(f"[USER_ANOMALY] Model trained and saved for user {user_id[:8]}...")
        return model
    
    def _check_retrain(self, user_id: str, history: List[Dict]):
        """Check if model needs retraining based on new data"""
        stats = self.user_stats.get(user_id, {'transactions_trained': 0})
        trained_on = stats.get('transactions_trained', 0)
        current = len(history)
        
        if current - trained_on >= self.RETRAIN_INTERVAL:
            print(f"[USER_ANOMALY] Retraining model for user {user_id[:8]}... ({current - trained_on} new transactions)")
            # Remove from cache to force retrain
            if user_id in self.user_models:
                del self.user_models[user_id]
            self._train_user_model(user_id, history)
    
    def _detect_with_model(self, model: IsolationForest, transactions: List[Dict]) -> List[Dict]:
        """Run anomaly detection with trained model"""
        if not transactions:
            return []
            
        results = []
        detect_txns = []
        for txn in transactions:
            t_type = str(txn.get('transaction_type', txn.get('type', ''))).lower()
            if t_type in {'credit', 'cr', 'received'}:
                results.append({**txn, 'is_anomaly': False, 'anomaly_score': 0.5,
                                'severity': 'low', 'detection_method': 'credit_skip'})
            else:
                detect_txns.append(txn)
                
        if not detect_txns:
            return results
        
        X = self._extract_features(detect_txns)
        predictions = model.predict(X)
        scores = model.decision_function(X)
        
        for i, txn in enumerate(detect_txns):
            ratio = float(X[i][3]) if X.shape[1] > 3 else 1.0
            results.append({
                **txn,
                'is_anomaly': bool(predictions[i] == -1),
                'anomaly_score': float(scores[i]),
                'severity': self._compute_severity(scores[i], ratio),
                'detection_method': 'user_model'
            })
        
        return results
    
    def _mark_all_normal(self, transactions: List[Dict], learning_phase: bool = False) -> List[Dict]:
        """Mark all transactions as normal (during learning phase)"""
        return [{
            **txn,
            'is_anomaly': False,
            'anomaly_score': 0.0,
            'severity': 'low',
            'detection_method': 'learning_phase' if learning_phase else 'fallback'
        } for txn in transactions]
    
    def _extract_features(self, transactions: List[Dict]) -> np.ndarray:
        features = []
        amounts_by_cat = {}
        for txn in transactions:
            cat = txn.get('category', 'Other')
            amounts_by_cat.setdefault(cat, []).append(float(txn.get('amount', 0)))

        for txn in transactions:
            amount = float(txn.get('amount', 0))
            cat = txn.get('category', 'Other')
            cat_id = self.category_map.get(cat, 8)
            cat_amounts = amounts_by_cat.get(cat, [amount])
            mean = np.mean(cat_amounts)
            std = max(float(np.std(cat_amounts)), 1.0)
            zscore = (amount - mean) / std
            ratio = amount / (mean + 1e-9)
            features.append([amount, cat_id, zscore, ratio])
        return np.array(features)
    
    def _compute_severity(self, score: float, ratio: float = 1.0) -> str:
        """Convert anomaly score & ratio to severity"""
        if ratio >= 3.0 or ratio <= 0.1:
            return "high"
        elif ratio >= 2.0 or ratio <= 0.15:
            return "medium"
        elif score < -0.15:
            return "medium"
        return "low"
    
    def _compute_stats(self, flagged: List[Dict]) -> Dict:
        """Compute anomaly statistics"""
        total = len(flagged)
        anomalies = len([t for t in flagged if t.get('is_anomaly', False)])
        
        return {
            'total': total,
            'anomalies': anomalies,
            'anomaly_count': anomalies,
            'anomaly_rate': anomalies / total if total > 0 else 0,
            'high_severity': len([t for t in flagged if t.get('severity') == 'high'])
        }
