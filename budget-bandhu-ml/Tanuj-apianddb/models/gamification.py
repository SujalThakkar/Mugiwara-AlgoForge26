"""Gamification Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class Badge(BaseModel):
    """Badge earned by user"""
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None
    
    # ML trigger condition (for display)
    trigger_description: str = ""


class LevelInfo(BaseModel):
    """User level information"""
    level: int = 1
    current_xp: int = 0
    xp_to_next_level: int = 100
    title: str = "Finance Beginner"
    
    @property
    def progress_percentage(self) -> float:
        return min(100, (self.current_xp / self.xp_to_next_level) * 100)


class Gamification(BaseModel):
    """Full gamification model (stored in MongoDB)"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    level_info: LevelInfo = Field(default_factory=LevelInfo)
    total_xp: int = 0
    badges: List[Badge] = []
    challenges_completed: int = 0
    streak_days: int = 0
    last_active: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


class XPEvent(BaseModel):
    """XP earned event"""
    amount: int
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ML-triggered badge definitions
ML_BADGES = [
    {
        "id": "transaction_master",
        "name": "Transaction Master",
        "description": "Log 50+ transactions",
        "icon": "📊",
        "trigger": "categorizer",
        "condition": "transactions_count >= 50",
        "xp_reward": 100
    },
    {
        "id": "anomaly_hunter",
        "name": "Anomaly Hunter",
        "description": "Detect your first suspicious transaction",
        "icon": "🔍",
        "trigger": "anomaly_detector",
        "condition": "anomalies_found >= 1",
        "xp_reward": 50
    },
    {
        "id": "savings_champion",
        "name": "Savings Champion",
        "description": "Maintain 20%+ savings rate",
        "icon": "💰",
        "trigger": "insights_generator",
        "condition": "savings_rate > 0.20",
        "xp_reward": 150
    },
    {
        "id": "financial_ninja",
        "name": "Financial Ninja",
        "description": "Achieve 850+ financial score",
        "icon": "🥷",
        "trigger": "insights_generator",
        "condition": "financial_score > 850",
        "xp_reward": 200
    },
    {
        "id": "budget_master",
        "name": "Budget Master",
        "description": "Stay under budget for all categories",
        "icon": "🎯",
        "trigger": "policy_learner",
        "condition": "all_categories_under_budget",
        "xp_reward": 100
    }
]


# XP rewards for actions
XP_REWARDS = {
    "add_transaction": 5,
    "upload_csv": 20,
    "set_budget": 25,
    "create_goal": 30,
    "contribute_to_goal": 10,
    "complete_goal": 100,
    "check_insights": 5,
    "daily_login": 10
}
