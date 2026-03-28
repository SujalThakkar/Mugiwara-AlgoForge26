import logging
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.database import Database, get_database
from models.schemas import Transaction, AnomalyAlert, SubscriptionPattern, KnowledgeGraphEdge, EdgeRelationship
from tools.financial_toolkit import detect_anomalies, detect_subscriptions

logger = logging.getLogger("BudgetBandhu.TransactionLoader")

router = APIRouter(prefix="/api/v1/transactions", tags=["Ingestion"])

class TransactionIngestionResponse(BaseModel):
    message: str
    anomalies: List[AnomalyAlert]
    subscriptions: List[SubscriptionPattern]
    transactions_saved: int
    user_id: str

@router.post("/single", response_model=TransactionIngestionResponse)
async def ingest_single(transaction: Transaction, db=Depends(get_database)):
    """Ingest a single transaction and run detector suite."""
    return await ingest_bulk([transaction], db=db, user_id=transaction.user_id)

@router.post("/bulk", response_model=TransactionIngestionResponse)
async def ingest_bulk_api(transactions: List[Transaction], db=Depends(get_database)):
    """Bulk ingest transactions and run detector suite."""
    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions provided")
    
    user_id = transactions[0].user_id
    if any(t.user_id != user_id for t in transactions):
        raise HTTPException(status_code=400, detail="All transactions in bulk must belong to the same user_id")
        
    return await ingest_bulk(transactions, db=db, user_id=user_id)

async def ingest_bulk(transactions: List[Transaction], db, user_id: str):
    """Internal logic for ingestion, detectors, and knowledge graph updates."""
    try:
        # 1. Save to Atlas 'transactions' collection
        txn_docs = [t.dict() for t in transactions]
        for doc in txn_docs:
            if "id" in doc and not doc["id"]:
                doc["id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.utcnow()
            
        if txn_docs:
            await db["transactions"].insert_many(txn_docs)
            
        # 2. Fetch full history for detection (last 90 days)
        # In a real app we'd query Mongo. For the hackathon we'll combine input + partial history.
        full_history_cursor = db["transactions"].find({"user_id": user_id}).sort("date", -1).limit(1000)
        full_history_docs = await full_history_cursor.to_list(length=1000)
        
        # Convert back to Transaction objects for toolkit
        full_history = []
        for d in full_history_docs:
            try:
                # Handle MongoDB ObjectId if present
                if "_id" in d: d.pop("_id")
                # Fix date parsing if stored as datetime
                full_history.append(Transaction(**d))
            except Exception as e:
                logger.warning(f"Failed to parse history transaction: {e}")

        # 3. Run Detectors
        anomalies = detect_anomalies(full_history)
        subscriptions = detect_subscriptions(full_history)
        
        # 4. Update Knowledge Graph (Categorical spending edges)
        await _update_kg_from_transactions(db, transactions, user_id)
        
        return TransactionIngestionResponse(
            message="Ingestion successful",
            anomalies=anomalies,
            subscriptions=subscriptions,
            transactions_saved=len(transactions),
            user_id=user_id
        )
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

async def _update_kg_from_transactions(db, transactions: List[Transaction], user_id: str):
    """
    Update KnowledgeGraphEdge collection based on transaction categories.
    E.g., if user spends heavily in a category, create/weight OVERSPENDS_ON edge.
    """
    cat_totals: Dict[str, float] = {}
    for t in transactions:
        if not t.is_credit:
            cat_totals[t.category] = cat_totals.get(t.category, 0) + t.amount
            
    for category, total in cat_totals.items():
        # Heuristic: If category spend > 5000 in this batch, strengthen the relationship
        if total > 5000:
            edge = {
                "user_id": user_id,
                "source_node": user_id,
                "source_type": "user",
                "relationship": EdgeRelationship.OVERSPENDS_ON.value,
                "target_node": category,
                "target_type": "category",
                "weight": 1.5,
                "evidence_count": 1,
                "last_updated": datetime.utcnow()
            }
            # Upsert into knowledge_graph collection
            await db["knowledge_graph"].update_one(
                {
                    "user_id": user_id, 
                    "source_node": user_id, 
                    "target_node": category, 
                    "relationship": EdgeRelationship.OVERSPENDS_ON.value
                },
                {"$inc": {"evidence_count": 1, "weight": 0.1}, "$set": {"last_updated": datetime.utcnow()}},
                upsert=True
            )
            logger.info(f"KG Updated: {user_id} {EdgeRelationship.OVERSPENDS_ON.value} {category}")
