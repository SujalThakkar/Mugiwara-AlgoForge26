import os
import json
import joblib
import numpy as np
import torch
import torch.nn as nn

MODEL_DIR = "models/lstm_forecaster"
CATEGORIES = ["Food & Dining", "Transport", "Shopping",
              "Entertainment", "Utilities & Bills", "Groceries"]


class BiLSTMForecaster(nn.Module):
    def __init__(self, n_features=6, hidden=128, n_layers=2,
                 forecast_days=7, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features, hidden_size=hidden,
            num_layers=n_layers, batch_first=True,
            bidirectional=True, dropout=dropout
        )
        self.bn = nn.BatchNorm1d(hidden * 2)
        self.fc1 = nn.Linear(hidden * 2, 64)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(64, forecast_days * n_features)
        self.forecast_days = forecast_days
        self.n_features = n_features

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        out = self.bn(out)
        out = self.dropout(self.relu(self.fc1(out)))
        out = self.fc2(out)
        return out.view(-1, self.forecast_days, self.n_features)


class ForecastResult:
    def __init__(self, forecast_by_day, forecast_by_category,
                 total_predicted_7d, total_predicted_30d,
                 savings_projected_30d, confidence, model_source):
        self.forecast_by_day = forecast_by_day
        self.forecast_by_category = forecast_by_category
        self.total_predicted_7d = total_predicted_7d
        self.total_predicted_30d = total_predicted_30d
        self.savings_projected_30d = savings_projected_30d
        self.confidence = confidence
        self.model_source = model_source

    def dict(self):
        return self.__dict__


class GoalFeasibilityReport:
    def __init__(self, goal_amount, current_savings,
                 monthly_surplus_needed, months_to_goal,
                 is_feasible, recommendation):
        self.goal_amount = goal_amount
        self.current_savings = current_savings
        self.monthly_surplus_needed = monthly_surplus_needed
        self.months_to_goal = months_to_goal
        self.is_feasible = is_feasible
        self.recommendation = recommendation


class SpendingForecaster:
    """
    Forecasts spending using PyTorch BiLSTM.
    Falls back to moving average if model not loaded.

    Example:
        forecaster = SpendingForecaster()
        result = forecaster.forecast(daily_history, days_ahead=7)
    """

    def __init__(self, model_dir: str = MODEL_DIR):
        self.model_dir = model_dir
        self._model = None
        self._scaler = None
        self._categories = CATEGORIES
        self._loaded = False
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._load_models()

    def _load_models(self):
        model_path = os.path.join(self.model_dir, "model.pt")
        scaler_path = os.path.join(self.model_dir, "scaler.joblib")
        cat_path = os.path.join(self.model_dir, "categories.json")

        if not all(os.path.exists(p) for p in [model_path, scaler_path]):
            print("[Forecaster] Model not found. Using moving average fallback.")
            return

        try:
            checkpoint = torch.load(model_path, map_location=self._device)
            cfg = checkpoint["model_config"]
            self._model = BiLSTMForecaster(**cfg).to(self._device)
            self._model.load_state_dict(checkpoint["model_state_dict"])
            self._model.eval()
            self._scaler = joblib.load(scaler_path)
            if os.path.exists(cat_path):
                with open(cat_path) as f:
                    self._categories = json.load(f)
            self._loaded = True
            print(f"[Forecaster] PyTorch BiLSTM loaded on {self._device}.")
        except Exception as e:
            print(f"[Forecaster] Load error: {e}. Using moving average fallback.")

    def is_loaded(self) -> bool:
        return self._loaded

    def _to_matrix(self, daily_history: list) -> np.ndarray:
        n_cats = len(self._categories)
        matrix = np.zeros((len(daily_history), n_cats), dtype=np.float32)
        for i, day in enumerate(daily_history):
            amounts = (day.category_amounts if hasattr(day, "category_amounts")
                       else day.get("category_amounts", {}))
            for j, cat in enumerate(self._categories):
                matrix[i, j] = float(amounts.get(cat, 0.0))
        return matrix

    def forecast(self, daily_history: list, days_ahead: int = 7) -> ForecastResult:
        if len(daily_history) < 7:
            return self._zero_forecast()
        matrix = self._to_matrix(daily_history)
        if self._loaded and len(daily_history) >= 30:
            return self._pytorch_forecast(matrix[-30:])
        return self._moving_average_forecast(matrix, days_ahead)

    def _pytorch_forecast(self, window: np.ndarray) -> ForecastResult:
        try:
            n_cats = len(self._categories)
            scaled = self._scaler.transform(window)
            x = torch.tensor(scaled, dtype=torch.float32).unsqueeze(0).to(self._device)
            with torch.no_grad():
                pred_scaled = self._model(x).squeeze(0).cpu().numpy()
            pred = self._scaler.inverse_transform(pred_scaled)
            pred = np.maximum(pred, 0)
            return self._build_result(pred, "bilstm_pytorch")
        except Exception as e:
            print(f"[Forecaster] Inference error: {e}")
            return self._moving_average_forecast(window, 7)

    def _moving_average_forecast(self, matrix: np.ndarray,
                                  days_ahead: int) -> ForecastResult:
        lookback = min(14, len(matrix))
        daily_avg = matrix[-lookback:].mean(axis=0)
        pred = np.tile(daily_avg, (days_ahead, 1))
        return self._build_result(np.maximum(pred, 0), "moving_average_fallback")

    def _build_result(self, pred: np.ndarray, source: str) -> ForecastResult:
        forecast_by_day = [
            {cat: round(float(val), 2)
             for cat, val in zip(self._categories, day)}
            for day in pred
        ]
        forecast_by_category = {
            cat: round(float(pred[:, j].sum()), 2)
            for j, cat in enumerate(self._categories)
        }
        total_7d = round(float(pred.sum()), 2)
        return ForecastResult(
            forecast_by_day=forecast_by_day,
            forecast_by_category=forecast_by_category,
            total_predicted_7d=total_7d,
            total_predicted_30d=round(total_7d * (30 / 7), 2),
            savings_projected_30d=0.0,
            confidence=0.87 if "bilstm" in source else 0.55,
            model_source=source,
        )

    def _zero_forecast(self) -> ForecastResult:
        empty = {cat: 0.0 for cat in self._categories}
        return ForecastResult(
            forecast_by_day=[empty] * 7,
            forecast_by_category=empty,
            total_predicted_7d=0.0, total_predicted_30d=0.0,
            savings_projected_30d=0.0, confidence=0.0,
            model_source="insufficient_data"
        )

    def check_goal_feasibility(self, goal_amount, current_savings,
                                monthly_income, forecast) -> GoalFeasibilityReport:
        remaining = goal_amount - current_savings
        monthly_spend = forecast.total_predicted_30d
        monthly_surplus = monthly_income - monthly_spend
        months = remaining / monthly_surplus if monthly_surplus > 0 else float("inf")
        feasible = monthly_surplus > 0 and months < 120
        rec = (
            f"At ₹{monthly_surplus:,.0f}/month surplus, goal in {months:.1f} months."
            if feasible else
            f"Projected spend ₹{monthly_spend:,.0f} exceeds income. "
            f"Reduce by ₹{max(0, monthly_spend - monthly_income + 500):,.0f}."
        )
        return GoalFeasibilityReport(
            goal_amount=goal_amount, current_savings=current_savings,
            monthly_surplus_needed=round(remaining / 12, 2),
            months_to_goal=round(months, 1),
            is_feasible=feasible, recommendation=rec
        )