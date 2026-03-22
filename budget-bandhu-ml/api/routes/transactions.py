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

# ML Imports (Assumes intelligence package is in root)
try:
    from intelligence.categorizer import TransactionCategorizer
    from intelligence.anomaly_detector import AnomalyDetector
    from intelligence.user_anomaly_detector import UserAnomalyDetector
    ML_AVAILABLE = True
except ImportError as e:
    print(f"[TRANSACTIONS] ⚠️ ML Components missing: {e}")
    ML_AVAILABLE = False

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])

# ML instances
categorizer = None
anomaly_detector = None
user_anomaly_detector = None

def set_ml_models(cat, ad, uad):
    global categorizer, anomaly_detector, user_anomaly_detector
    categorizer = cat
    anomaly_detector = ad
    user_anomaly_detector = uad
    logger.info("[TRANSACTIONS] ML Models injected into Route")


def process_through_ml_pipeline(transactions: List[dict], user_id: str = None, user_history: List[dict] = None) -> tuple:
    """
    Run transactions through the ML pipeline.
    Returns: (enriched_transactions, cat_stats, anomaly_stats)
    """
    cat_stats = {}
    anomaly_stats = {}
    
    # 1. Categorization (Independent)
    if categorizer:
        logger.info(f"🤖 [ML] Categorizing {len(transactions)} txns...")
        cat_result = categorizer.process({"transactions": transactions})
        categorized = cat_result["result"]
        cat_stats = cat_result["stats"]
    else:
        logger.warning("⚠️ Categorizer not loaded - using Uncategorized")
        categorized = []
        for t in transactions:
            t_copy = t.copy()
            t_copy.update({"category": "Uncategorized", "confidence": 0.0, "method": "fallback"})
            categorized.append(t_copy)
            
    # 2. Anomaly Detection (Independent)
    if anomaly_detector:
        logger.info(f"🤖 [ML] Anomaly check for {len(transactions)} txns...")
        if user_id and user_history:
            anomaly_result = user_anomaly_detector.process({
                "user_id": user_id,
                "transactions": categorized,
                "user_history": user_history
            })
        else:
            anomaly_result = anomaly_detector.process({"transactions": categorized})
            
        enriched = anomaly_result["result"]
        anomaly_stats = anomaly_result["stats"]
    else:
        logger.warning("⚠️ Anomaly Detector not loaded - skipping")
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
    user_id: str, 
    transaction: TransactionCreate, 
    db=Depends(get_database)
):
    """Add a single transaction (ML Processed)"""
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        # Prepare for ML pipeline
        txn_dict = {
            "date": str(transaction.date),
            "amount": transaction.amount,
            "description": transaction.description,
            "type": transaction.type
        }
        
        # Run pipeline
        enriched, _, _ = process_through_ml_pipeline([txn_dict], user_id=user_id)
        enriched_txn = enriched[0]
        
        # Mongo Document
        final_category = transaction.category if transaction.category else enriched_txn["category"]
        final_method = "manual" if transaction.category else enriched_txn.get("method", "manual")
        final_confidence = 1.0 if transaction.category else (enriched_txn.get("category_confidence") or enriched_txn.get("confidence", 0.0))

        doc = {
            "user_id": user_id,
            "date": transaction.date,
            "amount": transaction.amount,
            "description": transaction.description,
            "type": transaction.type,
            "notes": transaction.notes,
            # Enriched
            "category": final_category,
            "category_confidence": final_confidence,
            "categorization_method": final_method,
            "is_anomaly": enriched_txn["is_anomaly"],
            "anomaly_score": enriched_txn["anomaly_score"],
            "anomaly_severity": enriched_txn["severity"],
            "created_at": datetime.utcnow()
        }
        
        result = await db["transactions"].insert_one(doc)
        
        if transaction.type == 'debit':
            await update_budget_spent(db, user_id, final_category, transaction.amount)
        
        return {
            "message": "Transaction added",
            "transaction_id": str(result.inserted_id),
            "category": final_category,
            "is_anomaly": enriched_txn["is_anomaly"]
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
    
    enriched, cat_stats, anomaly_stats = process_through_ml_pipeline(
        txn_dicts, 
        user_id=data.user_id, 
        user_history=user_history
    )
    
    docs = []
    category_totals = {}
    
    for i, enriched_txn in enumerate(enriched):
        original = data.transactions[i]
        doc = {
            "user_id": data.user_id,
            **original.dict(),
            "category": enriched_txn["category"],
            "category_confidence": enriched_txn["confidence"],
            "categorization_method": enriched_txn["method"],
            "is_anomaly": enriched_txn["is_anomaly"],
            "anomaly_score": enriched_txn["anomaly_score"],
            "anomaly_severity": enriched_txn["severity"],
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
    # 1. Read file
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    
    # 2. Map columns (Case insensitive)
    # Expected: date, amount, description, [type, category]
    df.columns = [c.lower() for c in df.columns]
    
    # 3. Validation
    required = ["date", "amount", "description"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")
        
    # 4. Convert to list of dicts
    transactions = []
    for _, row in df.iterrows():
        transactions.append({
            "date": str(row["date"]),
            "amount": float(row["amount"]),
            "description": str(row["description"]),
            "type": row.get("type", "debit"),
            "category": row.get("category", None)
        })
        
    # 5. Reuse bulk logic
    from api.models.transaction import TransactionBulkUpload, TransactionCreate
    data = TransactionBulkUpload(
        user_id=user_id,
        transactions=[TransactionCreate(**t) for t in transactions]
    )
    
    return await add_transactions_bulk(data, db=db)



@router.get("/{user_id}", response_model=List[dict])
async def get_transactions(
    user_id: str,
    limit: int = 50,
    category: Optional[str] = None,
    anomalies_only: bool = False,
    db=Depends(get_database)
):
    """Get transactions"""
    query = {"user_id": user_id}
    if category: query["category"] = category
    if anomalies_only: query["is_anomaly"] = True
    
    cursor = db["transactions"].find(query).sort("date", -1).limit(limit)
    txns = await cursor.to_list(length=limit)
    
    # Fix ID
    for t in txns:
        t["id"] = str(t.pop("_id"))
        
    return txns


@router.get("/{user_id}/stats", response_model=TransactionStats)
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

