"""
LSTM Spending Forecaster - Production Version
Wrapper for trained LSTM with log1p + StandardScaler

Author: Tanuj
Date: Jan 16, 2026
"""
import torch
import torch.nn as nn
import numpy as np
import os
from typing import Dict, List
from sklearn.preprocessing import StandardScaler

from intelligence.base import IntelligenceComponent


class SafeLSTM(nn.Module):
    """LSTM architecture - must match training"""
    def __init__(self, hidden_size=32, num_layers=1):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True
        )
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class LSTMSavingsForecaster(IntelligenceComponent):
    """
    Forecasts spending for 7-day, 30-day, 90-day horizons.
    Uses log1p transform + StandardScaler for stable predictions.
    """
    
    def __init__(self, model_path: str):
        """
        Args:
            model_path: Path to trained LSTM checkpoint
        """
        print(f"[FORECASTER] Loading LSTM from {model_path}")
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Load checkpoint
        if os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # Check if new format (combined) or old format
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                # New format: checkpoint contains model + scaler
                self.window_size = checkpoint.get('window_size', 60)
                hidden_size = checkpoint.get('hidden_size', 32)
                num_layers = checkpoint.get('num_layers', 1)
                
                self.model = SafeLSTM(hidden_size, num_layers).to(self.device)
                self.model.load_state_dict(checkpoint['model_state_dict'])
                
                # Recreate scaler
                self.scaler = StandardScaler()
                self.scaler.mean_ = np.array(checkpoint['scaler_mean'])
                self.scaler.scale_ = np.array(checkpoint['scaler_scale'])
                self.scaler.var_ = self.scaler.scale_ ** 2
                self.scaler.n_features_in_ = 1
                
                print(f"[FORECASTER] Loaded v2 model (window={self.window_size}, hidden={hidden_size})")
            else:
                # Old format: just state_dict
                self.window_size = 30
                self.model = self._build_old_model()
                self.model.load_state_dict(checkpoint)
                self.scaler = None
                print("[FORECASTER] Loaded v1 model (legacy format)")
        else:
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        self.model.to(self.device)
        self.model.eval()
        print(f"[FORECASTER] Ready (device: {self.device})")
    
    def _build_old_model(self):
        """Legacy model architecture"""
        class OldLSTM(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(1, 64, 2, batch_first=True)
                self.fc = nn.Linear(64, 1)
            
            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                return self.fc(lstm_out[:, -1, :])
        return OldLSTM()
    
    def process(self, input_data: Dict) -> Dict:
        """
        Forecast spending.
        
        Input:
            {
                'historical_spending': [1000, 1200, 800, ...],
                'horizon': '7d' | '30d' | '90d',
                'current_balance': 50000 (optional)
            }
        
        Output:
            {
                'result': {
                    'predicted_spending': [...],
                    'predicted_savings': float (total),
                    'confidence': float,
                    'method': 'lstm'
                },
                'stats': {...}
            }
        """
        historical = np.array(input_data['historical_spending']).astype(np.float32)
        horizon = input_data.get('horizon', '30d')
        current_balance = input_data.get('current_balance', 0)
        
        forecast = self.forecast(historical, horizon)
        
        # Calculate predicted savings
        total_spending = sum(forecast['predicted_spending'])
        
        return {
            'result': {
                **forecast,
                'predicted_savings': current_balance - total_spending,
                'confidence': forecast.get('confidence', 0.75)
            },
            'stats': {'method': 'lstm', 'horizon': horizon}
        }
    
    def forecast(self, historical: np.ndarray, horizon: str) -> Dict:
        """Generate forecast using trained LSTM."""
        horizons = {'7d': 7, '30d': 30, '90d': 90}
        n_steps = horizons.get(horizon, 30)
        
        # Ensure enough data
        if len(historical) < self.window_size:
            # Pad with mean
            padding = np.full(self.window_size - len(historical), historical.mean())
            historical = np.concatenate([padding, historical])
        
        # Take last window_size days
        historical = historical[-self.window_size:]
        
        # Transform data
        if self.scaler:
            # New format: log1p + StandardScaler
            historical_log = np.log1p(historical).reshape(-1, 1)
            historical_scaled = self.scaler.transform(historical_log).flatten()
        else:
            # Old format: simple normalization (fallback)
            historical_scaled = (historical - historical.min()) / (historical.max() - historical.min() + 1e-8)
        
        # Prepare tensor
        input_tensor = torch.tensor(
            historical_scaled, dtype=torch.float32
        ).unsqueeze(0).unsqueeze(-1).to(self.device)
        
        # Generate predictions
        predictions_scaled = []
        with torch.no_grad():
            current_seq = input_tensor.clone()
            for _ in range(n_steps):
                pred = self.model(current_seq)
                predictions_scaled.append(pred.item())
                pred_val = pred.view(1, 1, 1)
                current_seq = torch.cat([current_seq[:, 1:, :], pred_val], dim=1)
        
        # Inverse transform
        if self.scaler:
            predictions_log = self.scaler.inverse_transform(
                np.array(predictions_scaled).reshape(-1, 1)
            )
            predictions = np.expm1(predictions_log).flatten()
        else:
            predictions = np.array(predictions_scaled) * (historical.max() - historical.min()) + historical.min()
        
        # Sanity clamp based on recent data
        recent = historical[-30:] if len(historical) >= 30 else historical
        median = np.median(recent)
        mad = np.median(np.abs(recent - median)) + 1e-6
        lower = max(0, median - 2.5 * mad)
        upper = median + 2.5 * mad
        predictions = np.clip(predictions, lower, upper)
        
        # Calculate confidence based on volatility
        cv = np.std(recent) / (np.mean(recent) + 1e-6)  # Coefficient of variation
        confidence = max(0.5, min(0.95, 1.0 - cv))
        
        return {
            'predicted_spending': predictions.tolist(),
            'confidence_intervals': [
                [p * (1 - 0.25 * (1 - confidence)), p * (1 + 0.25 * (1 - confidence))] 
                for p in predictions
            ],
            'method': 'lstm_v2' if self.scaler else 'lstm_v1',
            'input_mean': float(np.mean(historical)),
            'forecast_mean': float(np.mean(predictions)),
            'confidence': confidence,
            'trend': self._detect_trend(recent)
        }
    
    def _detect_trend(self, data: np.ndarray) -> str:
        """Detect spending trend based on linear regression slope"""
        if len(data) < 7:
            return 'stable'
        
        # Calculate trend as percentage of mean
        trend = np.polyfit(range(len(data)), data, 1)[0]
        data_mean = np.mean(data) + 1e-6
        trend_pct = (trend * len(data)) / data_mean  # Total change as % of mean
        
        if trend_pct > 0.3:  # 30% increase over period
            return 'increasing'
        elif trend_pct < -0.3:  # 30% decrease
            return 'decreasing'
        return 'stable'

