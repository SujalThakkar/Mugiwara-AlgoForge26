"""User Pydantic Models - Mobile Number ID (12 Digits)"""
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    """Schema for creating a new user (Mobile Auth)"""
    mobile: str = Field(..., description="Mobile Number (10 or 12 digits)")
    name: str = Field(..., min_length=2, max_length=100)
    income: float = Field(..., gt=0, description="Monthly income in INR")
    password: str = Field(..., min_length=4, description="PIN or Password")
    
    @validator("mobile")
    def validate_mobile(cls, v):
        # Remove any non-digits
        digits = "".join(filter(str.isdigit, v))
        
        if len(digits) == 10:
            # Append 91 for India
            return "91" + digits
        elif len(digits) == 12:
            if not digits.startswith("91"):
                 raise ValueError("12-digit number must start with 91 (India Code)")
            return digits
        else:
            raise ValueError("Mobile number must be 10 digits or 12 digits (starting with 91)")

class UserLogin(BaseModel):
    """Schema for user login"""
    mobile: str
    password: str
    
    @validator("mobile")
    def validate_mobile(cls, v):
        digits = "".join(filter(str.isdigit, v))
        if len(digits) == 10:
            return "91" + digits
        if len(digits) == 12 and digits.startswith("91"):
            return digits
        raise ValueError("Mobile number must be 10 digits or 12 digits (starting with 91)")

class User(BaseModel):
    """Full user model (internal)"""
    id: str = Field(..., alias="_id")  # Mobile Number (12 digits)
    name: str
    income: float
    password_hash: str
    currency: str = "INR"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True

class UserResponse(BaseModel):
    """User response"""
    id: str
    name: str
    income: float
    currency: str
    created_at: datetime
    
    class Config:
        from_attributes = True
