"""
Integration wrapper for Tanuj's ML models
Provides unified interface for categorization, forecasting, and anomaly detection.

Author: Aryan Lomte (Integration), Tanuj (Models)
Date: Jan 16, 2026
"""
import os
import sys
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime, timedelta

# Import Tanuj's components with CORRECT class names
CATEGORIZER_AVAILABLE = False
FORECASTER_AVAILABLE = False
ANOMALY_AVAILABLE = False
USER_ANOMALY_AVAILABLE = False

print("[TANUJ] Attempting to load ML models...")

try:
    from intelligence.categorizer import TransactionCategorizer
    CATEGORIZER_AVAILABLE = True
    print("[TANUJ] ✅ TransactionCategorizer imported")
except ImportError as e:
    print(f"[TANUJ] ⚠️ Categorizer not available: {e}")

try:
    from intelligence.forecaster import LSTMSavingsForecaster
    FORECASTER_AVAILABLE = True
    print("[TANUJ] ✅ LSTMSavingsForecaster imported")
except ImportError as e:
    print(f"[TANUJ] ⚠️ Forecaster not available: {e}")

try:
    from intelligence.anomaly_detector import AnomalyDetector
    ANOMALY_AVAILABLE = True
    print("[TANUJ] ✅ AnomalyDetector imported")
except ImportError as e:
    print(f"[TANUJ] ⚠️ Anomaly detector not available: {e}")

try:
    from intelligence.user_anomaly_detector import UserAnomalyDetector
    USER_ANOMALY_AVAILABLE = True
    print("[TANUJ] ✅ UserAnomalyDetector imported")
except ImportError as e:
    print(f"[TANUJ] ⚠️ User anomaly detector not available: {e}")


class TanujMLService:
    """
    Unified service for Tanuj's ML models.
    Handles categorization, forecasting, and anomaly detection.
    """
    
    def __init__(self):
        """Initialize all available models"""
        self.categorizer = None
        self.forecaster = None
        self.anomaly_detector = None
        self.user_anomaly_detector = None
        
        print("[TANUJ] Initializing ML service...")
        
        # ============================================================
        # Initialize Categorizer (NO MODEL PATH NEEDED - RULE-BASED)
        # ============================================================
        if CATEGORIZER_AVAILABLE:
            try:
                # TransactionCategorizer uses rule-based + optional Phi-3.5
                # For now, just rule-based (phi3_model_path=None)
                self.categorizer = TransactionCategorizer(phi3_model_path=None)
                print("[TANUJ] ✅ Categorizer initialized (rule-based mode)")
            except Exception as e:
                print(f"[TANUJ] ⚠️ Categorizer init failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ============================================================
        # Initialize Forecaster (NEEDS MODEL PATH)
        # ============================================================
        if FORECASTER_AVAILABLE:
            try:
                # Find LSTM model file
                model_paths = [
                    "models/lstm_forecaster/lstm_checkpoint.pth",
                    "models/lstm_forecaster/model.pth",
                    "models/lstm_forecaster/best_model.pth",
                    "models/lstm_forecaster/lstm_model.pth"
                ]
                
                model_path = None
                for path in model_paths:
                    if os.path.exists(path):
                        model_path = path
                        break
                
                if model_path:
                    self.forecaster = LSTMSavingsForecaster(model_path)
                    print(f"[TANUJ] ✅ Forecaster initialized with {model_path}")
                else:
                    print("[TANUJ] ⚠️ No LSTM model file found. Tried:")
                    for path in model_paths:
                        print(f"       - {path}")
            except Exception as e:
                print(f"[TANUJ] ⚠️ Forecaster init failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ============================================================
        # Initialize Anomaly Detector (NEEDS MODEL + CATEGORY MAP)
        # ============================================================
        if ANOMALY_AVAILABLE:
            try:
                model_path = "models/isolation_forest/model.pkl" 
                category_map_path = "models/isolation_forest/category_map.json"
                
                if os.path.exists(model_path) and os.path.exists(category_map_path):
                    self.anomaly_detector = AnomalyDetector(model_path, category_map_path)
                    print("[TANUJ] ✅ Anomaly detector initialized")
                else:
                    print(f"[TANUJ] ⚠️ Anomaly detector files not found:")
                    print(f"       - {model_path}: {os.path.exists(model_path)}")
                    print(f"       - {category_map_path}: {os.path.exists(category_map_path)}")
            except Exception as e:
                print(f"[TANUJ] ⚠️ Anomaly detector init failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ============================================================
        # Initialize User Anomaly Detector (OPTIONAL)
        # ============================================================
        if USER_ANOMALY_AVAILABLE:
            try:
                self.user_anomaly_detector = UserAnomalyDetector(
                    models_dir="models/user_anomaly",
                    category_map_path="models/isolation_forest/category_map.json"
                )
                print("[TANUJ] ✅ User anomaly detector initialized")
            except Exception as e:
                print(f"[TANUJ] ⚠️ User anomaly detector init failed: {e}")
        
        print(f"[TANUJ] Service initialized:")
        print(f"  • Categorizer: {bool(self.categorizer)}")
        print(f"  • Forecaster: {bool(self.forecaster)}")
        print(f"  • Anomaly Detector: {bool(self.anomaly_detector)}")
        print(f"  • User Anomaly: {bool(self.user_anomaly_detector)}")
    
    def categorize_expense(self, description: str, amount: float) -> Dict:
        """
        Categorize a single expense.
        
        Args:
            description: Expense description
            amount: Amount in rupees
        
        Returns:
            {'category': str, 'confidence': float, 'method': str}
        """
        if self.categorizer:
            try:
                # Tanuj's categorizer expects batch format
                result = self.categorizer.process({
                    'transactions': [{'description': description, 'amount': amount}]
                })
                
                # Extract first result
                if result['result']:
                    first = result['result'][0]
                    return {
                        'category': first.get('category', 'Other'),
                        'confidence': first.get('confidence', 0.75),
                        'method': first.get('method', 'rule')
                    }
            except Exception as e:
                print(f"[TANUJ] Categorization error: {e}")
                import traceback
                traceback.print_exc()
        
        return self._fallback_categorize(description, amount)
    
    def forecast_expenses(
        self,
        user_id: int,
        historical_data: Optional[List[Dict]] = None,
        months: int = 3
    ) -> Dict:
        """
        Forecast future expenses.
        
        Args:
            user_id: User ID
            historical_data: List of past transactions
            months: Number of months to forecast
        
        Returns:
            {'predictions': List[Dict], 'method': str}
        """
        if self.forecaster and historical_data and len(historical_data) >= 30:
            try:
                # Extract spending amounts from transactions
                amounts = [abs(float(txn.get('amount', 0))) for txn in historical_data]
                
                # Map months to horizon
                horizon_map = {1: '7d', 3: '30d', 6: '90d'}
                horizon = horizon_map.get(months, '30d')
                
                # Call Tanuj's forecaster
                result = self.forecaster.process({
                    'historical_spending': amounts,
                    'horizon': horizon,
                    'current_balance': 50000  # Default
                })
                
                # Convert to our format
                predictions = result['result']['predicted_spending']
                month_names = ['Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul']
                
                formatted = []
                for i, amount in enumerate(predictions[:months]):
                    formatted.append({
                        'month': f'{month_names[i % len(month_names)]} 2026',
                        'amount': round(amount, 2),
                        'confidence': result['result'].get('confidence', 0.75)
                    })
                
                return {
                    'predictions': formatted,
                    'method': 'lstm_model',
                    'trend': result['result'].get('trend', 'stable')
                }
            except Exception as e:
                print(f"[TANUJ] Forecasting error: {e}")
                import traceback
                traceback.print_exc()
        
        return self._fallback_forecast(historical_data or [], months)
    
    def detect_anomaly(self, transaction: Dict) -> Dict:
        """
        Detect if transaction is anomalous.
        
        Args:
            transaction: {'description': str, 'amount': float, 'category': str}
        
        Returns:
            {'is_anomaly': bool, 'anomaly_score': float, 'reason': str}
        """
        if self.anomaly_detector:
            try:
                # Tanuj's detector expects batch format
                result = self.anomaly_detector.process({
                    'transactions': [transaction]
                })
                
                if result['result']:
                    first = result['result'][0]
                    return {
                        'is_anomaly': first.get('is_anomaly', False),
                        'anomaly_score': first.get('anomaly_score', 0.0),
                        'reason': f"Severity: {first.get('severity', 'low')}",
                        'method': 'isolation_forest'
                    }
            except Exception as e:
                print(f"[TANUJ] Anomaly detection error: {e}")
                import traceback
                traceback.print_exc()
        
        return self._fallback_anomaly(transaction)
    
    def generate_insights(self, user_id: int, transactions: List[Dict]) -> Dict:
        """Generate spending insights"""
        if not transactions:
            return {
                'insights': [],
                'total_spend': 0,
                'category_breakdown': {},
                'recommendations': ['Start adding expenses to get personalized insights!']
            }
        
        # Aggregate by category
        category_totals = {}
        total_spend = 0
        
        for txn in transactions:
            category = txn.get('category', 'Other')
            amount = abs(txn.get('amount', 0))
            category_totals[category] = category_totals.get(category, 0) + amount
            total_spend += amount
        
        # Generate insights
        insights = []
        for category, amount in category_totals.items():
            percentage = (amount / total_spend * 100) if total_spend > 0 else 0
            if percentage > 25:
                insights.append({
                    'type': 'overspend',
                    'category': category,
                    'amount': round(amount, 2),
                    'percentage': round(percentage, 1),
                    'message': f'High spending in {category}: ₹{amount:,.0f} ({percentage:.1f}%)'
                })
        
        return {
            'insights': insights,
            'total_spend': round(total_spend, 2),
            'category_breakdown': {k: round(v, 2) for k, v in category_totals.items()},
            'recommendations': self._generate_recommendations(insights, total_spend)
        }
    
    # ============================================================
    # FALLBACK METHODS
    # ============================================================
    
    def _fallback_categorize(self, description: str, amount: float) -> Dict:
        """Rule-based categorization fallback"""
        desc_lower = description.lower()
        
        categories = {
            'Food & Drink': ['food', 'restaurant', 'cafe', 'coffee', 'swiggy', 'zomato'],
            'Travel': ['uber', 'ola', 'taxi', 'metro', 'petrol', 'fuel'],
            'Shopping': ['amazon', 'flipkart', 'shopping', 'myntra'],
            'Entertainment': ['netflix', 'spotify', 'movie', 'cinema'],
            'Utilities': ['electricity', 'water', 'internet', 'phone', 'bill'],
            'Rent': ['rent'],
            'Groceries': ['grocery', 'dmart', 'vegetables']
        }
        
        for category, keywords in categories.items():
            if any(kw in desc_lower for kw in keywords):
                return {'category': category, 'confidence': 0.75, 'method': 'rule_based_fallback'}
        
        return {'category': 'Other', 'confidence': 0.5, 'method': 'rule_based_fallback'}
    
    def _fallback_forecast(self, historical_data: List[Dict], months: int) -> Dict:
        """Simple average forecasting"""
        if not historical_data:
            base_amount = 40000
        else:
            amounts = [abs(txn.get('amount', 0)) for txn in historical_data]
            base_amount = sum(amounts) / len(amounts) if amounts else 40000
        
        predictions = []
        month_names = ['Feb', 'Mar', 'Apr', 'May', 'Jun']
        
        for i in range(months):
            predictions.append({
                'month': f'{month_names[i]} 2026',
                'amount': round(base_amount * (1 + i * 0.02), 2),
                'confidence': 0.65
            })
        
        return {'predictions': predictions, 'method': 'average_fallback'}
    
    def _fallback_anomaly(self, transaction: Dict) -> Dict:
        """Threshold-based anomaly detection"""
        amount = abs(transaction.get('amount', 0))
        threshold = 30000
        is_anomaly = amount > threshold
        
        return {
            'is_anomaly': is_anomaly,
            'anomaly_score': min(amount / 60000, 1.0),
            'reason': f'Amount exceeds ₹{threshold:,}' if is_anomaly else 'Normal',
            'method': 'threshold_fallback'
        }
    
    def _generate_recommendations(self, insights: List[Dict], total_spend: float) -> List[str]:
        """Generate recommendations"""
        recs = []
        for insight in insights:
            if insight['type'] == 'overspend':
                recs.append(f"💡 Reduce {insight['category']} by 10-15%")
        
        if not recs:
            recs.append("✅ Your spending looks balanced!")
        
        return recs


# Singleton
_tanuj_service = None

def get_tanuj_service() -> TanujMLService:
    """Get singleton instance"""
    global _tanuj_service
    if _tanuj_service is None:
        _tanuj_service = TanujMLService()
    return _tanuj_service


# Test
if __name__ == "__main__":
    print("=" * 70)
    print("TESTING TANUJ ML SERVICE")
    print("=" * 70)
    
    service = get_tanuj_service()
    
    print("\n1. Testing Categorization:")
    result = service.categorize_expense("Swiggy food order", 450)
    print(f"   Result: {result}")
    
    print("\n2. Testing Forecasting:")
    result = service.forecast_expenses(1, [], 3)
    print(f"   Result: {result}")
    
    print("\n3. Testing Anomaly Detection:")
    result = service.detect_anomaly({'description': 'Large withdrawal', 'amount': 75000, 'category': 'Cash'})
    print(f"   Result: {result}")
    
    print("\n" + "=" * 70)
    print("✅ Integration wrapper tested!")
