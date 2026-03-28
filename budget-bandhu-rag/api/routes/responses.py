from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from datetime import datetime, timedelta
from api.database import get_database
from models.schemas import FinalResponse, RetrievalAudit, ConfidenceTier

router = APIRouter(prefix="/api/v1", tags=["Analytics & Audits"])

@router.get("/response/{query_id}", response_model=Dict[str, Any])
async def get_response(query_id: str, db=Depends(get_database)):
    """Retrieve a previously generated FinalResponse by query_id."""
    resp = await db["responses"].find_one({"query_id": query_id})
    if not resp:
        raise HTTPException(status_code=404, detail="Response not found")
    if "_id" in resp: resp.pop("_id")
    return resp

@router.get("/audit/{query_id}", response_model=RetrievalAudit)
async def get_audit(query_id: str, db=Depends(get_database)):
    """Retrieve retrieval audit details for a specific query."""
    audit = await db["audits"].find_one({"query_id": query_id})
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if "_id" in audit: audit.pop("_id")
    return RetrievalAudit(**audit)

@router.get("/audit/user/{user_id}", response_model=List[RetrievalAudit])
async def get_user_audits(user_id: str, limit: int = 20, db=Depends(get_database)):
    """Retrieve last N audits for a specific user."""
    cursor = db["audits"].find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    audits = await cursor.to_list(length=limit)
    for a in audits:
        if "_id" in a: a.pop("_id")
    return [RetrievalAudit(**a) for a in audits]

@router.get("/analytics/confidence/{user_id}")
async def get_confidence_analytics(user_id: str, db=Depends(get_database)):
    """HIGH/MEDIUM/LOW counts per week for last 4 weeks."""
    four_weeks_ago = datetime.utcnow() - timedelta(weeks=4)
    
    pipeline = [
        {
            "$match": {
                "user_id": user_id,
                "created_at": {"$gte": four_weeks_ago}
            }
        },
        {
            "$group": {
                "_id": {
                    "week": {"$week": "$created_at"},
                    "confidence": "$confidence_tier"
                },
                "count": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id.week": 1}
        }
    ]
    
    results = await db["audits"].aggregate(pipeline).to_list(length=100)
    
    # Format for frontend
    analytics = {}
    for r in results:
        week = f"Week {r['_id']['week']}"
        conf = r['_id']['confidence']
        if week not in analytics:
            analytics[week] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        analytics[week][conf] = r["count"]
        
    return analytics

@router.get("/analytics/memory/{user_id}")
async def get_memory_analytics(user_id: str, db=Depends(get_database)):
    """Tier contribution distribution over last 30 days."""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    cursor = db["audits"].find(
        {"user_id": user_id, "created_at": {"$gte": thirty_days_ago}},
        {"retrieval_sources": 1}
    )
    
    tier_counts = {"WORKING": 0, "EPISODIC": 0, "SEMANTIC": 0, "PROCEDURAL": 0, "TRAJECTORY": 0}
    
    async for audit in cursor:
        sources = audit.get("retrieval_sources", {})
        for tier, count in sources.items():
            if tier in tier_counts:
                tier_counts[tier] += count
                
    return tier_counts
