"""
Transaction Routes - CRUD + ML Pipeline (Categorizer + AnomalyDetector)
BudgetBandhu API

Transactions flow through ML pipeline before storage:
1. Categorizer assigns category + confidence
2. AnomalyDetector flags suspicious transactions
3. Enriched transaction stored in MongoDB
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import pandas as pd
import io

from api.database import get_database
from api.models.transaction import (
    TransactionCreate, TransactionBulkUpload, Transaction, 
    TransactionResponse, TransactionStats
)
from intelligence.categorizer import TransactionCategorizer
from intelligence.anomaly_detector import AnomalyDetector
from intelligence.user_anomaly_detector import UserAnomalyDetector

router = APIRouter(prefix="/api/v1/transactions", tags=["Transactions"])

# Initialize ML models (singleton)
print("[TRANSACTIONS] Loading ML models...")
categorizer = TransactionCategorizer(phi3_model_path="models/phi3_categorizer")

# Global fallback anomaly detector (for new users with <30 transactions)
anomaly_detector = AnomalyDetector(
    model_path="models/isolation_forest/model.pkl",
    category_map_path="models/isolation_forest/category_map.json"
)

# Per-user adaptive anomaly detector (trains on user's own history)
user_anomaly_detector = UserAnomalyDetector(
    models_dir="models/user_anomaly",
    category_map_path="models/isolation_forest/category_map.json"
)
print("[TRANSACTIONS] ML models loaded successfully (including per-user anomaly detector)")


def process_through_ml_pipeline(transactions: List[dict], user_id: str = None, user_history: List[dict] = None) -> List[dict]:
    """
    Run transactions through the ML pipeline:
    1. Categorizer → assigns category
    2. AnomalyDetector → flags anomalies (per-user adaptive)
    
    Args:
        transactions: New transactions to process
        user_id: User ID for per-user anomaly detection
        user_history: User's historical transactions for training
    """
    from datetime import datetime
    import pandas as pd
    
    print("\n" + "=" * 80)
    print("🤖 [ML PIPELINE] Starting transaction processing...")
    print(f"📊 [ML PIPELINE] Input: {len(transactions)} transactions")
    if user_id:
        print(f"👤 [ML PIPELINE] User: {user_id[:8]}...")
    print("=" * 80)
    
    # Step 1: Categorize
    print("\n" + "─" * 80)
    print("📌 [STEP 1/2] 🏷️  CATEGORIZER (Phi-3.5 + Rule-based)")
    print("─" * 80)
    cat_result = categorizer.process({"transactions": transactions})
    categorized = cat_result["result"]
    cat_stats = cat_result["stats"]
    
    # Detailed per-entry categorization log
    print("\n┌" + "─" * 78 + "┐")
    print(f"│ {'#':<3} {'DATE':<12} {'DAY':<5} {'AMOUNT':>10} {'CATEGORY':<18} {'METHOD':<8} │")
    print("├" + "─" * 78 + "┤")
    
    for i, t in enumerate(categorized, 1):
        # Parse time variables
        try:
            dt = pd.to_datetime(t.get('date', ''))
            day_name = dt.strftime('%a')  # Mon, Tue, etc.
            hour = dt.strftime('%H:%M') if hasattr(dt, 'hour') else '--:--'
            day_of_week = dt.dayofweek  # 0=Mon, 6=Sun
            is_weekend = "🟡" if day_of_week >= 5 else "  "
        except:
            day_name = "---"
            hour = "--:--"
            is_weekend = "  "
        
        method = t.get('method', 'rule')
        method_tag = "📜 RULE" if method == 'rule' else "🧠 LLM "
        category = t.get('category', 'Other')[:16]
        amount = t.get('amount', 0)
        date_str = str(t.get('date', ''))[:10]
        
        print(f"│ {i:<3} {date_str:<12} {day_name:<5} ₹{amount:>8,.0f} {category:<18} {method_tag:<8} │")
    
    print("└" + "─" * 78 + "┘")
    
    # Summary stats
    print(f"\n  📈 Categorization Summary:")
    print(f"      ├─ 📜 Rule-based: {cat_stats.get('rule_based', 0)} transactions")
    print(f"      ├─ 🧠 Phi-3.5 LLM: {cat_stats.get('phi3', 0)} transactions")
    print(f"      └─ ❓ Unknown/Other: {cat_stats.get('unknown', 0)} transactions")
    
    # Category breakdown
    print(f"\n  📊 Category Distribution:")
    category_counts = {}
    category_amounts = {}
    for t in categorized:
        cat = t.get("category", "Unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        category_amounts[cat] = category_amounts.get(cat, 0) + t.get("amount", 0)
    
    for cat, count in sorted(category_counts.items(), key=lambda x: -category_amounts[x[0]]):
        pct = (count / len(categorized)) * 100
        total_amt = category_amounts[cat]
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"      {cat:<18} {bar} {count:>2} ({pct:>5.1f}%) ₹{total_amt:>10,.0f}")
    
    # Step 2: Anomaly detection (PER-USER if possible)
    print("\n" + "─" * 80)
    
    if user_id and user_history is not None:
        history_count = len(user_history)
        print(f"📌 [STEP 2/2] 🔍 ANOMALY DETECTOR (Per-User Adaptive | {history_count} history)")
        print("─" * 80)
        
        # Use per-user detector
        anomaly_result = user_anomaly_detector.process({
            "user_id": user_id,
            "transactions": categorized,
            "user_history": user_history
        })
        
        # Check if in learning phase
        if anomaly_result.get('user_learning_phase'):
            print(f"  ⏳ Learning Phase: Need {30 - history_count} more transactions for personalized detection")
    else:
        print("📌 [STEP 2/2] 🔍 ANOMALY DETECTOR (Global Fallback)")
        print("─" * 80)
        anomaly_result = anomaly_detector.process({"transactions": categorized})
    
    enriched = anomaly_result["result"]
    anomaly_stats = anomaly_result["stats"]
    
    # Detailed per-entry anomaly log
    print("\n┌" + "─" * 78 + "┐")
    print(f"│ {'#':<3} {'AMOUNT':>10} {'CATEGORY':<16} {'SCORE':>8} {'STATUS':<12} {'SEVERITY':<10} │")
    print("├" + "─" * 78 + "┤")
    
    for i, t in enumerate(enriched, 1):
        amount = t.get('amount', 0)
        category = t.get('category', 'Other')[:14]
        score = t.get('anomaly_score', 0)
        is_anomaly = t.get('is_anomaly', False)
        severity = t.get('severity', 'low')
        
        # Status with emoji
        if is_anomaly:
            status = "🚨 ANOMALY"
            severity_icon = {"high": "🔴 HIGH", "medium": "🟠 MEDIUM", "low": "🟡 LOW"}.get(severity, "⚪ ---")
        else:
            status = "✅ NORMAL"
            severity_icon = "🟢 OK"
        
        print(f"│ {i:<3} ₹{amount:>9,.0f} {category:<16} {score:>+8.4f} {status:<12} {severity_icon:<10} │")
    
    print("└" + "─" * 78 + "┘")
    
    # Anomaly summary
    anomaly_count = anomaly_stats.get('anomalies', 0)
    print(f"\n  🔍 Anomaly Detection Summary:")
    print(f"      ├─ Total analyzed: {len(categorized)}")
    print(f"      ├─ ✅ Normal: {len(categorized) - anomaly_count}")
    print(f"      └─ 🚨 Anomalies: {anomaly_count}")
    
    if anomaly_count > 0:
        print(f"\n  ⚠️  Flagged Transactions:")
        for t in enriched:
            if t.get("is_anomaly"):
                severity = t.get("severity", "unknown")
                emoji = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(severity, "⚪")
                print(f"      {emoji} ₹{t.get('amount', 0):>10,.0f} │ {t.get('description', 'N/A')[:40]} │ Score: {t.get('anomaly_score', 0):+.4f}")
    
    print("\n" + "=" * 80)
    print("✅ [ML PIPELINE] Processing complete!")
    print("=" * 80 + "\n")
    
    return enriched, cat_stats, anomaly_stats


@router.post("", response_model=dict)
async def add_transaction(
    user_id: str,
    transaction: TransactionCreate,
    db=Depends(get_database)
):
    """
    Add a single transaction.
    Runs through ML pipeline before storage.
    """
    # Prepare for ML pipeline
    txn_dict = {
        "date": transaction.date,
        "amount": transaction.amount,
        "description": transaction.description,
        "type": transaction.type
    }
    
    # Run through ML pipeline
    enriched, cat_stats, anomaly_stats = process_through_ml_pipeline([txn_dict])
    enriched_txn = enriched[0]
    
    # Prepare document for MongoDB
    doc = {
        "user_id": user_id,
        "date": transaction.date,
        "amount": transaction.amount,
        "description": transaction.description,
        "type": transaction.type,
        "notes": transaction.notes,
        # ML-enriched fields
        "category": enriched_txn["category"],
        "category_confidence": enriched_txn["confidence"],
        "categorization_method": enriched_txn["method"],
        "is_anomaly": enriched_txn["is_anomaly"],
        "anomaly_score": enriched_txn["anomaly_score"],
        "anomaly_severity": enriched_txn["severity"],
        "created_at": datetime.utcnow()
    }
    
    # Store in MongoDB
    result = await db["transactions"].insert_one(doc)
    
    # Update budget spent amount for this category
    await update_budget_spent(db, user_id, enriched_txn["category"], transaction.amount)
    
    print(f"[TRANSACTIONS] Added: {transaction.description[:30]} → {enriched_txn['category']} (anomaly={enriched_txn['is_anomaly']})")
    
    return {
        "message": "Transaction added",
        "transaction_id": str(result.inserted_id),
        "category": enriched_txn["category"],
        "is_anomaly": enriched_txn["is_anomaly"],
        "anomaly_severity": enriched_txn["severity"]
    }


@router.post("/bulk", response_model=dict)
async def add_transactions_bulk(
    data: TransactionBulkUpload,
    db=Depends(get_database)
):
    """
    Bulk upload transactions (from CSV or batch).
    All transactions run through ML pipeline with per-user anomaly detection.
    """
    if not data.transactions:
        raise HTTPException(status_code=400, detail="No transactions provided")
    
    # Fetch user's transaction history for per-user anomaly detection
    user_history = []
    try:
        cursor = db["transactions"].find(
            {"user_id": data.user_id},
            {"amount": 1, "category": 1, "date": 1, "description": 1}
        ).sort("date", -1).limit(500)  # Last 500 transactions
        user_history = await cursor.to_list(length=500)
        print(f"[TRANSACTIONS] Loaded {len(user_history)} historical transactions for user {data.user_id[:8]}...")
    except Exception as e:
        print(f"[TRANSACTIONS] Could not load user history: {e}")
    
    # Prepare for ML pipeline
    txn_dicts = [
        {
            "date": t.date,
            "amount": t.amount,
            "description": t.description,
            "type": t.type
        }
        for t in data.transactions
    ]
    
    # Run through ML pipeline with user context
    enriched, cat_stats, anomaly_stats = process_through_ml_pipeline(
        txn_dicts, 
        user_id=data.user_id,
        user_history=user_history
    )
    
    # Prepare documents for MongoDB
    docs = []
    category_totals = {}  # For budget updates
    
    for i, enriched_txn in enumerate(enriched):
        original = data.transactions[i]
        doc = {
            "user_id": data.user_id,
            "date": original.date,
            "amount": original.amount,
            "description": original.description,
            "type": original.type,
            "notes": original.notes,
            # ML-enriched fields
            "category": enriched_txn["category"],
            "category_confidence": enriched_txn["confidence"],
            "categorization_method": enriched_txn["method"],
            "is_anomaly": enriched_txn["is_anomaly"],
            "anomaly_score": enriched_txn["anomaly_score"],
            "anomaly_severity": enriched_txn["severity"],
            "created_at": datetime.utcnow()
        }
        docs.append(doc)
        
        # Accumulate for budget update
        cat = enriched_txn["category"]
        if original.type == "debit":
            category_totals[cat] = category_totals.get(cat, 0) + original.amount
    
    # Bulk insert
    result = await db["transactions"].insert_many(docs)
    
    # Update budget spent for each category
    for category, total in category_totals.items():
        await update_budget_spent(db, data.user_id, category, total)
    
    print(f"[TRANSACTIONS] Bulk added: {len(docs)} transactions")
    
    return {
        "message": f"Added {len(docs)} transactions",
        "inserted_count": len(result.inserted_ids),
        "categorization_stats": cat_stats,
        "anomaly_stats": anomaly_stats
    }


@router.post("/upload-csv", response_model=dict)
async def upload_csv(
    user_id: str,
    file: UploadFile = File(...),
    db=Depends(get_database)
):
    """
    Upload transactions from CSV file.
    Expected columns: date, amount, description, type (optional)
    """
    print("\n" + "🌟" * 30)
    print("[CSV UPLOAD] FILE RECEIVED")
    print("🌟" * 30)
    print(f"  📁 Filename: {file.filename}")
    print(f"  👤 User ID: {user_id}")
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    # Read CSV
    content = await file.read()
    print(f"  📊 File size: {len(content):,} bytes")
    
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")
    
    print(f"  📋 Rows: {len(df)}")
    print(f"  📑 Columns: {list(df.columns)}")
    
    # Validate required columns
    required_cols = ["date", "amount", "description"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")
    
    # Calculate totals before processing
    total_amount = df["amount"].sum()
    print(f"  💰 Total amount: ₹{total_amount:,.2f}")
    print("\n  ⏳ Starting ML Pipeline processing...")
    
    # Convert to transaction list
    transactions = []
    for _, row in df.iterrows():
        transactions.append(TransactionCreate(
            date=str(row["date"]),
            amount=float(row["amount"]),
            description=str(row["description"]),
            type=str(row.get("type", "debit")).lower(),
            notes=str(row.get("notes", "")) if "notes" in df.columns else None
        ))
    
    # Use bulk upload
    bulk_data = TransactionBulkUpload(user_id=user_id, transactions=transactions)
    result = await add_transactions_bulk(bulk_data, db)
    
    print("\n" + "✅" * 30)
    print("[CSV UPLOAD] COMPLETE")
    print("✅" * 30)
    print(f"  📊 Inserted: {result['inserted_count']} transactions")
    print(f"  🏷️  Categories: {len(result['categorization_stats'])} types")
    print(f"  🚨 Anomalies: {result['anomaly_stats'].get('anomaly_count', 0)}")
    print("=" * 60 + "\n")
    
    return result


@router.get("/{user_id}", response_model=List[dict])
async def get_transactions(
    user_id: str,
    limit: int = 50,
    skip: int = 0,
    category: Optional[str] = None,
    anomalies_only: bool = False,
    db=Depends(get_database)
):
    """Get user's transactions with optional filters"""
    query = {"user_id": user_id}
    
    if category:
        query["category"] = category
    if anomalies_only:
        query["is_anomaly"] = True
    
    cursor = db["transactions"].find(query).sort("date", -1).skip(skip).limit(limit)
    transactions = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string
    for txn in transactions:
        txn["id"] = str(txn.pop("_id"))
    
    return transactions


@router.get("/{user_id}/stats", response_model=dict)
async def get_transaction_stats(user_id: str, db=Depends(get_database)):
    """Get transaction statistics for user"""
    collection = db["transactions"]
    
    # Total count
    total = await collection.count_documents({"user_id": user_id})
    
    # Anomaly count
    anomalies = await collection.count_documents({"user_id": user_id, "is_anomaly": True})
    
    # Category breakdown
    pipeline = [
        {"$match": {"user_id": user_id, "type": "debit"}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    category_breakdown = await collection.aggregate(pipeline).to_list(length=100)
    
    return {
        "total_transactions": total,
        "total_anomalies": anomalies,
        "anomaly_rate": anomalies / total if total > 0 else 0,
        "category_breakdown": {item["_id"]: {"total": item["total"], "count": item["count"]} for item in category_breakdown}
    }


@router.get("/{user_id}/anomalies", response_model=List[dict])
async def get_anomalies(user_id: str, db=Depends(get_database)):
    """Get all flagged anomalies for user"""
    cursor = db["transactions"].find({
        "user_id": user_id,
        "is_anomaly": True
    }).sort("anomaly_score", 1)  # Most severe first (more negative = more anomalous)
    
    anomalies = await cursor.to_list(length=100)
    
    for txn in anomalies:
        txn["id"] = str(txn.pop("_id"))
    
    return anomalies


async def update_budget_spent(db, user_id: str, category: str, amount: float):
    """Update spent amount in budget for a category"""
    await db["budgets"].update_one(
        {"user_id": user_id, "allocations.category": category},
        {"$inc": {"allocations.$.spent": amount}}
    )
