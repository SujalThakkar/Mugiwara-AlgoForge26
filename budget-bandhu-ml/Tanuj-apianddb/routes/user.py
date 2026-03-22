"""
User Routes - Registration, Login, Profile
BudgetBandhu API
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime
from passlib.context import CryptContext
from bson import ObjectId

from api.database import get_database
from api.models.user import UserCreate, UserLogin, UserResponse
from api.models.budget import generate_default_budget, BudgetAllocation
from api.models.gamification import LevelInfo, ML_BADGES, Badge

router = APIRouter(prefix="/api/v1/user", tags=["User"])

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


@router.post("/register", response_model=UserResponse)
async def register_user(user_data: UserCreate, db=Depends(get_database)):
    """
    Register a new user.
    Auto-creates default budget and gamification profile.
    """
    users_collection = db["users"]
    
    # Check if email exists
    existing = await users_collection.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user document
    user_doc = {
        "name": user_data.name,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "income": user_data.income,
        "currency": "INR",
        "created_at": datetime.utcnow()
    }
    
    result = await users_collection.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    # Auto-create default budget based on income
    budgets_collection = db["budgets"]
    default_allocations = generate_default_budget(user_data.income)
    budget_doc = {
        "user_id": user_id,
        "total_income": user_data.income,
        "allocations": [a.model_dump() for a in default_allocations],
        "savings_target": user_data.income * 0.20,  # 20% savings target
        "current_savings": 0.0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await budgets_collection.insert_one(budget_doc)
    
    # Auto-create gamification profile
    gamification_collection = db["gamification"]
    # Initialize badges as locked
    badges = []
    for badge_def in ML_BADGES:
        badges.append({
            "id": badge_def["id"],
            "name": badge_def["name"],
            "description": badge_def["description"],
            "icon": badge_def["icon"],
            "unlocked": False,
            "unlocked_at": None,
            "trigger_description": badge_def["condition"]
        })
    
    gamification_doc = {
        "user_id": user_id,
        "level_info": LevelInfo().model_dump(),
        "total_xp": 0,
        "badges": badges,
        "challenges_completed": 0,
        "streak_days": 0,
        "last_active": datetime.utcnow(),
        "created_at": datetime.utcnow()
    }
    await gamification_collection.insert_one(gamification_doc)
    
    print(f"[USER] Registered: {user_data.email} with default budget and gamification")
    
    return UserResponse(
        id=user_id,
        name=user_data.name,
        email=user_data.email,
        income=user_data.income,
        currency="INR",
        created_at=user_doc["created_at"]
    )


@router.post("/login")
async def login_user(login_data: UserLogin, db=Depends(get_database)):
    """
    Login user and return user info.
    (Simple auth - no JWT for prototype)
    """
    users_collection = db["users"]
    
    user = await users_collection.find_one({"email": login_data.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(login_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Update last active in gamification
    await db["gamification"].update_one(
        {"user_id": str(user["_id"])},
        {"$set": {"last_active": datetime.utcnow()}}
    )
    
    print(f"[USER] Login: {login_data.email}")
    
    return {
        "message": "Login successful",
        "user": UserResponse(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            income=user["income"],
            currency=user.get("currency", "INR"),
            created_at=user["created_at"]
        )
    }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_profile(user_id: str, db=Depends(get_database)):
    """Get user profile by ID"""
    users_collection = db["users"]
    
    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        income=user["income"],
        currency=user.get("currency", "INR"),
        created_at=user["created_at"]
    )


@router.put("/{user_id}/income")
async def update_income(user_id: str, income: float, db=Depends(get_database)):
    """Update user's monthly income"""
    if income <= 0:
        raise HTTPException(status_code=400, detail="Income must be positive")
    
    users_collection = db["users"]
    
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"income": income}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Income updated", "new_income": income}
