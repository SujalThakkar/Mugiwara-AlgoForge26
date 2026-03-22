"""Budget Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class BudgetAllocation(BaseModel):
    """Single category allocation"""
    category: str
    allocated: float = Field(..., ge=0, description="Allocated amount for this category")
    spent: float = Field(default=0.0, ge=0, description="Amount spent so far")
    
    @property
    def remaining(self) -> float:
        return max(0, self.allocated - self.spent)
    
    @property
    def percentage_used(self) -> float:
        if self.allocated == 0:
            return 0
        return min(100, (self.spent / self.allocated) * 100)


class BudgetCreate(BaseModel):
    """Schema for creating/updating budget"""
    user_id: str
    total_income: float = Field(..., gt=0)
    allocations: List[BudgetAllocation]


class Budget(BaseModel):
    """Full budget model (stored in MongoDB)"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    total_income: float
    allocations: List[BudgetAllocation]
    savings_target: float = 0.0
    current_savings: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


class BudgetRecommendation(BaseModel):
    """ML-generated budget recommendation (from PolicyLearner)"""
    category: str
    current_allocation: float
    actual_spent: float
    recommended: float
    multiplier: float
    change: str  # "increase", "decrease", "maintain"
    reason: str


class BudgetRecommendationResponse(BaseModel):
    """Response containing all budget recommendations"""
    user_id: str
    recommendations: List[BudgetRecommendation]
    total_savings_potential: float
    method: str = "policy_learning"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# Default budget allocations based on 50/30/20 rule (Indian context)
DEFAULT_ALLOCATIONS = [
    {"category": "Rent", "percentage": 25},
    {"category": "Food & Drink", "percentage": 15},
    {"category": "Utilities", "percentage": 8},
    {"category": "Transport", "percentage": 8},
    {"category": "Shopping", "percentage": 8},
    {"category": "Entertainment", "percentage": 5},
    {"category": "Health & Fitness", "percentage": 4},
    {"category": "Education", "percentage": 3},
    {"category": "Personal Care", "percentage": 2},
    {"category": "Insurance", "percentage": 4},
    {"category": "EMI", "percentage": 8},
    {"category": "Investment", "percentage": 10},
]


def generate_default_budget(income: float) -> List[BudgetAllocation]:
    """Generate default budget allocations based on income"""
    allocations = []
    for item in DEFAULT_ALLOCATIONS:
        allocated = (item["percentage"] / 100) * income
        allocations.append(BudgetAllocation(
            category=item["category"],
            allocated=round(allocated, 0),
            spent=0.0
        ))
    return allocations
