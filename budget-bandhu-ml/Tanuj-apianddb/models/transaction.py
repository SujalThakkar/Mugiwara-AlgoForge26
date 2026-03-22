"""Transaction Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class TransactionCreate(BaseModel):
    """Schema for creating/uploading a transaction"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    amount: float = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=500)
    type: Literal["debit", "credit"] = "debit"
    notes: Optional[str] = None


class TransactionBulkUpload(BaseModel):
    """Schema for bulk CSV upload"""
    user_id: str
    transactions: List[TransactionCreate]


class Transaction(BaseModel):
    """Full transaction model (stored in MongoDB)"""
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    date: str
    amount: float
    description: str
    type: Literal["debit", "credit"] = "debit"
    notes: Optional[str] = None
    
    # ML-enriched fields (from Categorizer)
    category: str = "Other"
    category_confidence: float = 0.0
    categorization_method: Literal["rule", "phi3", "manual"] = "rule"
    
    # ML-enriched fields (from AnomalyDetector)
    is_anomaly: bool = False
    anomaly_score: float = 0.0
    anomaly_severity: Literal["normal", "low", "medium", "high"] = "normal"
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


class TransactionResponse(BaseModel):
    """Transaction response for API"""
    id: str
    user_id: str
    date: str
    amount: float
    description: str
    type: str
    category: str
    category_confidence: float
    is_anomaly: bool
    anomaly_severity: str
    notes: Optional[str] = None
    created_at: datetime


class TransactionStats(BaseModel):
    """Statistics after processing transactions"""
    total: int
    rule_based: int
    phi3: int
    unknown: int
    anomalies: int
    high_severity: int
