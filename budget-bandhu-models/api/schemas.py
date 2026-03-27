from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class Transaction(BaseModel):
    transaction_id: str
    date: str
    description: str
    amount: float
    transaction_type: str  # Debit | Credit
    balance: float
    category: Optional[str] = None

class CategoryResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    category: str
    confidence: float
    alternatives: list[tuple[str, float]] = []
    model_version: str = "1.0"

class CategorizedTransaction(BaseModel):
    transaction: Transaction
    category_result: CategoryResult

class AnomalyResult(BaseModel):
    model_config = {"protected_namespaces": ()}
    transaction_id: str
    is_anomaly: bool
    anomaly_score: float
    anomaly_type: Optional[str] = None  # SPIKE|DUPLICATE|OFF_HOURS|NEW_MERCHANT|VELOCITY
    severity: str = "LOW"               # LOW|MEDIUM|HIGH
    reason: str
    model_source: str = "isolation_forest"

class DailySpend(BaseModel):
    date: str
    category_amounts: dict[str, float]

class ForecastResult(BaseModel):
    forecast_by_day: list[dict[str, float]]
    forecast_by_category: dict[str, float]
    total_predicted_7d: float
    total_predicted_30d: float
    savings_projected_30d: float
    confidence: float
    model_source: str = "lstm"

class GoalFeasibilityReport(BaseModel):
    goal_amount: float
    current_savings: float
    monthly_surplus_needed: float
    months_to_goal: float
    is_feasible: bool
    recommendation: str

class UserFinancialState(BaseModel):
    monthly_income: float
    current_savings_rate: float
    goal_progress: float = 0.0
    category_spend: dict[str, float] = {}
    budget_allocations: dict[str, float] = {}

class BudgetRecommendation(BaseModel):
    action_id: int
    action_name: str
    new_allocations: dict[str, float]
    reasoning: str
    expected_savings_improvement: float
    confidence: float

class ModelHealthReport(BaseModel):
    categorizer_loaded: bool
    anomaly_detector_loaded: bool
    forecaster_loaded: bool
    policy_learner_loaded: bool
    all_healthy: bool

class MLPipelineResult(BaseModel):
    user_id: str
    transactions_parsed: int
    transactions_categorized: list[CategorizedTransaction]
    anomalies_detected: list[AnomalyResult]
    high_severity_anomalies: int
    forecast_7d: Optional[ForecastResult] = None
    budget_recommendation: Optional[BudgetRecommendation] = None
    category_breakdown: dict[str, float]
    total_spend: float
    total_income: float
    net_savings: float
    savings_rate: float
    processing_time_ms: int
    models_used: list[str]

class CategorizeRequest(BaseModel):
    descriptions: list[str]

class AnomalyRequest(BaseModel):
    transactions: list[Transaction]
    history: list[Transaction]

class ForecastRequest(BaseModel):
    daily_history: list[DailySpend]
    days_ahead: int = 7