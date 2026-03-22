"""Goal Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class Milestone(BaseModel):
    """Goal milestone"""
    amount: float
    reached: bool = False
    date: Optional[str] = None


class GoalCreate(BaseModel):
    """Schema for creating a goal"""
    user_id: str
    name: str = Field(..., min_length=2, max_length=100)
    icon: str = "🎯"
    target: float = Field(..., gt=0)
    deadline: str = Field(..., description="Date in YYYY-MM-DD format")
    priority: Literal["low", "medium", "high"] = "medium"
    color: str = "#3B82F6"


class Goal(BaseModel):
    """Full goal model (stored in MongoDB)"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    name: str
    icon: str = "🎯"
    target: float
    current: float = 0.0
    deadline: str
    priority: Literal["low", "medium", "high"] = "medium"
    color: str = "#3B82F6"
    milestones: List[Milestone] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
    
    @property
    def progress_percentage(self) -> float:
        if self.target == 0:
            return 0
        return min(100, (self.current / self.target) * 100)
    
    @property
    def remaining(self) -> float:
        return max(0, self.target - self.current)


class GoalResponse(BaseModel):
    """Goal response for API"""
    id: str
    user_id: str
    name: str
    icon: str
    target: float
    current: float
    deadline: str
    priority: str
    color: str
    progress_percentage: float
    remaining: float
    milestones: List[Milestone]
    # ML-enriched fields (from LSTMForecaster)
    eta_days: Optional[int] = None
    on_track: bool = True


class GoalContribution(BaseModel):
    """Schema for adding money to a goal"""
    amount: float = Field(..., gt=0)
