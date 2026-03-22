"""User Pydantic Models"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from bson import ObjectId


class PyObjectId(str):
    """Custom type for MongoDB ObjectId"""
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return v
        raise ValueError("Invalid ObjectId")


class UserCreate(BaseModel):
    """Schema for creating a new user"""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    income: float = Field(..., gt=0, description="Monthly income in INR")


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class User(BaseModel):
    """Full user model (internal)"""
    id: Optional[str] = Field(None, alias="_id")
    name: str
    email: str
    password_hash: str
    income: float
    currency: str = "INR"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}


class UserResponse(BaseModel):
    """User response (excludes password)"""
    id: str
    name: str
    email: str
    income: float
    currency: str = "INR"
    created_at: datetime
    
    class Config:
        from_attributes = True
