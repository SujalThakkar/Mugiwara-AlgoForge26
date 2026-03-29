"""
Transaction Routes - CRUD + ML Pipeline
BudgetBandhu API

Features:
- ML Categorization (Phi-3.5 + Rules)
- Anomaly Detection (Isolation Forest)
- Mobile ID support
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Optional
from datetime import datetime
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

from api.database import get_database
from api.models.transaction import (
    TransactionCreate, TransactionBulkUpload, Transaction, 
    TransactionResponse, TransactionStats
)
from pydantic import BaseModel
from typing import Any

# ML Imports
from intelligence.ml_client import categorize, detect_anomalies
from intelligence.user_anomaly_detector import UserAnomalyDetector

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])

class TransactionCreateRequest(BaseModel):
    """Flexible transaction body — accepts user_id inline and transaction_type alias."""
    user_id: str = "+91-9876543210"
    description: str
    amount: float
    transaction_type: Optional[str] = "Debit"  # Debit / Credit (case-insensitive)
    type: Optional[str] = None                  # alternative field name
    date: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None

    def resolved_type(self) -> str:
        raw = (self.type or self.transaction_type or "Debit").lower()
        return "debit" if raw == "debit" else "credit"

# ML instances
user_anomaly_detector: Optional[UserAnomalyDetector] = None

def set_ml_models(uad: Optional[UserAnomalyDetector]):
    global user_anomaly_detector
    user_anomaly_detector = uad
    logger.info("[TRANSACTIONS] UserAnomalyDetector injected into Route")


async def process_through_ml_pipeline(transactions: List[dict], user_id: str = None, user_history: List[dict] = None) -> tuple:
    """
    Run transactions through the ML pipeline via HTTP.
    Returns: (enriched_transactions, cat_stats, anomaly_stats)
    """
    cat_stats = {}
    anomaly_stats = {}
    
    # 1. Categorization (Remote HTTP)
    logger.info(f"🤖 [ML] Categorizing {len(transactions)} txns via budget-bandhu-models...")
    try:
        descriptions = [t.get("description", "") for t in transactions]
        cat_result = await categorize(descriptions)
        
        ml_results = cat_result.get("results", [])
        categorized = []
        for i, t in enumerate(transactions):
            t_copy = t.copy()
            # Handle results as list of dicts or list of strings
            if i < len(ml_results):
                res = ml_results[i]
                if isinstance(res, dict):
                    t_copy["category"] = res.get("category", "Uncategorized")
                    t_copy["confidence"] = res.get("confidence", 0.95)
                else:
                    t_copy["category"] = str(res)
                    t_copy["confidence"] = 0.95
            else:
                t_copy["category"] = "Uncategorized"
                t_copy["confidence"] = 0.0
            
            t_copy["method"] = "llm"
            categorized.append(t_copy)
            
        cat_stats = cat_result.get("stats", {})
    except Exception as e:
        logger.warning(f"⚠️ Categorizer failed - using Uncategorized: {e}")
        categorized = []
        for t in transactions:
            t_copy = t.copy()
            t_copy.update({"category": "Uncategorized", "confidence": 0.0, "method": "fallback"})
            categorized.append(t_copy)
            
    # 2. Anomaly Detection (Remote HTTP & Local User Anomaly)
    logger.info(f"🤖 [ML] Anomaly check for {len(transactions)} txns...")
    try:
        # We run the basic remote isolation forest first
        anomaly_result = await detect_anomalies(categorized)
        
        remote_anomalies = anomaly_result.get("anomalies", [])
        enriched = []
        for i, t in enumerate(categorized):
            t_copy = t.copy()
            if i < len(remote_anomalies):
                anom = remote_anomalies[i]
                t_copy["is_anomaly"] = anom.get("is_anomaly", False)
                t_copy["anomaly_score"] = anom.get("anomaly_score", 0.0)
                t_copy["severity"] = anom.get("severity", "LOW")
                t_copy["reason"] = anom.get("reason", "")
            enriched.append(t_copy)
            
        anomaly_stats = anomaly_result.get("stats", {})
        
        # Overlay user anomaly detector if history is passed
        if user_id and user_history and user_anomaly_detector:
            uad_result = user_anomaly_detector.process({
                "user_id": user_id,
                "transactions": enriched,
                "user_history": user_history
            })
            enriched = uad_result["result"]
            anomaly_stats.update(uad_result.get("stats", {}))
    except Exception as e:
        logger.warning(f"⚠️ Anomaly Detector failed - skipping: {e}")
        enriched = []
        for t in categorized:
            t.update({"is_anomaly": False, "anomaly_score": 0.0, "severity": "normal"})
            enriched.append(t)
            
    return enriched, cat_stats, anomaly_stats


async def update_budget_spent(db, user_id: str, category: str, amount: float):
    """Update spent amount in budget for a category"""
    await db["budgets"].update_one(
        {"user_id": user_id, "allocations.category": category},
        {"$inc": {"allocations.$.spent": amount}}
    )


@router.post("", response_model=dict)
async def add_transaction(
    request: TransactionCreateRequest,
    db=Depends(get_database)
):
    """Add a single transaction (ML Processed) — accepts user_id in body."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        user_id = request.user_id
        txn_type = request.resolved_type()
        txn_date = request.date or datetime.utcnow().strftime("%Y-%m-%d")

        txn_dict = {
            "date": txn_date,
            "amount": request.amount,
            "description": request.description,
            "type": txn_type
        }

        # Run ML pipeline
        enriched, _, _ = await process_through_ml_pipeline([txn_dict], user_id=user_id)
        enriched_txn = enriched[0]

        final_category = request.category if request.category else enriched_txn.get("category", "Other")
        final_method   = "manual" if request.category else enriched_txn.get("method", "ml")
        final_confidence = 1.0 if request.category else enriched_txn.get("confidence", 0.0)

        is_anomaly     = enriched_txn.get("is_anomaly", False)
        anomaly_score  = enriched_txn.get("anomaly_score", 0.0)
        anomaly_sev    = enriched_txn.get("severity") or enriched_txn.get("anomaly_severity")
        anomaly_reason = enriched_txn.get("reason") or enriched_txn.get("anomaly_reason")

        doc = {
            "user_id": user_id,
            "date": txn_date,
            "amount": request.amount,
            "description": request.description,
            "type": txn_type,
            "notes": request.notes,
            "category": final_category,
            "category_confidence": final_confidence,
            "categorization_method": final_method,
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
            "anomaly_severity": anomaly_sev,
            "anomaly_reason": anomaly_reason,
            "anomaly_flagged_at": datetime.utcnow() if is_anomaly else None,
            "created_at": datetime.utcnow()
        }

        result = await db["transactions"].insert_one(doc)

        if txn_type == "debit":
            await update_budget_spent(db, user_id, final_category, request.amount)

        return {
            "message": "Transaction added",
            "transaction_id": str(result.inserted_id),
            "category": final_category,
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
            "anomaly_severity": anomaly_sev,
        }
    except Exception as e:
        import traceback
        print(f"ERROR ADDING TRANSACTION: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=dict)
async def add_transactions_bulk(
    data: TransactionBulkUpload,
    db=Depends(get_database)
):
    """Bulk upload transactions"""
    if not data.transactions:
        raise HTTPException(status_code=400, detail="No transactions")
        
    # Get user history for anomaly detection
    user_history = await db["transactions"].find(
        {"user_id": data.user_id},
        {"amount": 1, "category": 1, "date": 1, "description": 1}
    ).sort("date", -1).limit(500).to_list(length=500)
    
    txn_dicts = [t.dict() for t in data.transactions]
    
    enriched, cat_stats, anomaly_stats = await process_through_ml_pipeline(
        txn_dicts, 
        user_id=data.user_id, 
        user_history=user_history
    )
    
    docs = []
    category_totals = {}
    
    for i, enriched_txn in enumerate(enriched):
        original = data.transactions[i]
        is_anomaly     = enriched_txn.get("is_anomaly", False)
        anomaly_score  = enriched_txn.get("anomaly_score", 0.0)
        anomaly_sev    = enriched_txn.get("severity") or enriched_txn.get("anomaly_severity")
        anomaly_type   = enriched_txn.get("anomaly_type") or enriched_txn.get("type")
        anomaly_reason = enriched_txn.get("reason") or enriched_txn.get("anomaly_reason")
        doc = {
            "user_id": data.user_id,
            **original.dict(),
            "category": enriched_txn["category"],
            "category_confidence": enriched_txn.get("confidence", 0.0),
            "categorization_method": enriched_txn.get("method", "ml"),
            "is_anomaly": is_anomaly,
            "anomaly_score": anomaly_score,
            "anomaly_severity": anomaly_sev,
            "anomaly_type": anomaly_type,
            "anomaly_reason": anomaly_reason,
            "anomaly_flagged_at": datetime.utcnow() if is_anomaly else None,
            "created_at": datetime.utcnow()
        }
        docs.append(doc)
        
        if original.type == 'debit':
            cat = enriched_txn["category"]
            category_totals[cat] = category_totals.get(cat, 0) + original.amount
            
    if docs:
        result = await db["transactions"].insert_many(docs)
        
        for cat, total in category_totals.items():
            await update_budget_spent(db, data.user_id, cat, total)
            
    return {
        "message": f"Added {len(docs)} transactions",
        "categorization_stats": cat_stats,
        "anomaly_stats": anomaly_stats
    }


@router.post("/upload-csv", response_model=dict)
async def upload_csv(
    user_id: str,
    file: UploadFile = File(...),
    db=Depends(get_database)
):
    """Upload transactions via CSV"""
    try:
        # 1. Read file
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        
        # 2. Map columns (Case insensitive)
        df.columns = [c.lower().strip() for c in df.columns]
        
        # 3. Validation
        required = ["date", "amount", "description"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")
            
        # 4. Convert to list of dicts (pandas-safe access, no .get())
        transactions = []
        for _, row in df.iterrows():
            txn_type = str(row["type"]).strip().lower() if "type" in df.columns else "debit"
            cat = row["category"] if "category" in df.columns and pd.notna(row["category"]) else None
            transactions.append({
                "date": str(row["date"]),
                "amount": float(row["amount"]),
                "description": str(row["description"]),
                "type": txn_type if txn_type in ("debit", "credit") else "debit",
                "category": cat if cat and str(cat).lower() not in ("nan", "none", "") else None
            })
            
        # 5. Reuse bulk logic
        from api.models.transaction import TransactionBulkUpload, TransactionCreate
        data = TransactionBulkUpload(
            user_id=user_id,
            transactions=[TransactionCreate(**t) for t in transactions]
        )
        
        result = await add_transactions_bulk(data, db=db)
        result["transactions_parsed"] = len(transactions)
        result["inserted_count"] = len(transactions)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CSV Upload] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/{user_id}", response_model=List[dict])
async def get_transactions(
    user_id: str,
    limit: int = 1000,
    category: Optional[str] = None,
    anomalies_only: bool = False,
    db=Depends(get_database)
):
    """Get transactions"""
    query = {"user_id": user_id}
    if category: query["category"] = category
    if anomalies_only: query["is_anomaly"] = True

    sort_field = "anomaly_score" if anomalies_only else "date"
    sort_dir   = -1  # always descending
    cursor = db["transactions"].find(query).sort(sort_field, sort_dir).limit(limit)
    txns = await cursor.to_list(length=limit)
    
    # Fix ID
    for t in txns:
        t["id"] = str(t.pop("_id"))
        
    return txns


@router.get("/{user_id}/stats", response_model=dict)
async def get_transaction_stats(user_id: str, db=Depends(get_database)):
    """Get transaction statistics for a user"""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$facet": {
            "overall": [
                {"$group": {
                    "_id": None,
                    "total_count": {"$sum": 1},
                    "anomaly_count": {"$sum": {"$cond": [{"$eq": ["$is_anomaly", True]}, 1, 0]}}
                }}
            ],
            "categories": [
                {"$match": {"type": "debit"}},
                {"$group": {
                    "_id": "$category",
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1}
                }}
            ]
        }}
    ]
    
    result = await db["transactions"].aggregate(pipeline).to_list(length=1)
    if not result:
        return {"total_transactions": 0, "total_anomalies": 0, "anomaly_rate": 0, "category_breakdown": {}}
    
    data = result[0]
    overall = data["overall"][0] if data["overall"] else {"total_count": 0, "anomaly_count": 0}
    
    category_breakdown = {
        cat["_id"]: {"total": cat["total"], "count": cat["count"]}
        for cat in data["categories"]
    }
    
    total = overall["total_count"]
    anomalies = overall["anomaly_count"]
    
    return {
        "total_transactions": total,
        "total_anomalies": anomalies,
        "anomaly_rate": (anomalies / total * 100) if total > 0 else 0,
        "category_breakdown": category_breakdown
    }


@router.get("/{user_id}/anomalies", response_model=List[dict])
async def get_anomalies(user_id: str, limit: int = 50, db=Depends(get_database)):
    """Get only anomalous transactions"""
    cursor = db["transactions"].find({"user_id": user_id, "is_anomaly": True}).sort("date", -1).limit(limit)
    txns = await cursor.to_list(length=limit)
    for t in txns:
        t["id"] = str(t.pop("_id"))
    return txns

