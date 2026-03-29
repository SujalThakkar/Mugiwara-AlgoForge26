import pandas as pd
from pymongo import MongoClient
import uuid
import datetime
from datetime import timedelta

# ── CONFIG ──
ATLAS_URI = "mongodb+srv://aryanlomte_db_user:1o1s26Syatgt2b5R@cluster0.0mw7kni.mongodb.net/?appName=Cluster0"
DB_NAME = "budget_bandhu"
TARGET_USER = "917558497556"
SOURCE_USER = "demo_user_001"
CSV_PATH = r"C:\Users\Aryan\Downloads\test_transactions_3months.csv"

def get_logical_category(description: str) -> str:
    desc = str(description).lower()
    if any(k in desc for k in ['zomato', 'swiggy', 'domino', 'restaurant', 'mcdonald', 'chai point', 'starbucks', 'food']):
        return 'Food & Dining'
    elif any(k in desc for k in ['uber', 'ola', 'rapido', 'metro', 'dmrc', 'irctc', 'flight']):
        return 'Transport'
    elif any(k in desc for k in ['rent', 'maintenance', 'society']):
        return 'Housing'
    elif any(k in desc for k in ['zepto', 'blinkit', 'bigbasket', 'grocery', 'dmart']):
        return 'Groceries'
    elif any(k in desc for k in ['amazon', 'flipkart', 'myntra', 'nykaa', 'shopping', 'decathlon']):
        return 'Shopping'
    elif any(k in desc for k in ['bill', 'electricity', 'bescom', 'tata power', 'broadband', 'recharge', 'jio', 'emi']):
        return 'Utilities'
    elif any(k in desc for k in ['netflix', 'spotify', 'bookmyshow', 'pvr', 'hotstar', 'steam']):
        return 'Entertainment'
    elif any(k in desc for k in ['salary', 'freelance']):
        return 'Income'
    elif any(k in desc for k in ['mutual fund', 'sip', 'elss', 'lic']):
        return 'Investment'
    elif any(k in desc for k in ['apollo', '1mg', 'cult', 'fitness']):
        return 'Health & Fitness'
    elif any(k in desc for k in ['friend', 'upi']):
        return 'Transfer'
    else:
        return 'Other'

def seed():
    print("Connecting to Atlas...")
    client = MongoClient(ATLAS_URI)
    db = client[DB_NAME]

    print("1. Wiping old data (excluding SOURCE and TARGET)...")
    collections_with_user_id = [
        "transactions", "bills", "goals", 
        "agent_episodic_memory", "agent_semantic_memory", 
        "agent_procedural_memory", "agent_working_memory", 
        "agent_trajectory_memory", "knowledge_graph"
    ]
    
    # Drop all extraneous noise
    for coll in collections_with_user_id:
        db[coll].delete_many({"user_id": {"$nin": [SOURCE_USER, TARGET_USER]}})
    # Drop unknown users
    db.users.delete_many({"_id": {"$nin": [SOURCE_USER, TARGET_USER]}})

    print(f"2. Migrating data from {SOURCE_USER} to {TARGET_USER}...")
    # Migrate any collections
    migrated_count = 0
    for coll in collections_with_user_id:
        res = db[coll].update_many(
            {"user_id": SOURCE_USER},
            {"$set": {"user_id": TARGET_USER}}
        )
        migrated_count += res.modified_count
    print(f"   -> Migrated {migrated_count} records across {len(collections_with_user_id)} collections.")

    # Migrate the User document itself
    user_doc = db.users.find_one({"_id": SOURCE_USER})
    if user_doc:
        print(f"   -> Found user doc for {SOURCE_USER}. Moving to {TARGET_USER}.")
        db.users.delete_one({"_id": SOURCE_USER})
        user_doc["_id"] = TARGET_USER
        db.users.delete_one({"_id": TARGET_USER}) # Overwrite if exists
        db.users.insert_one(user_doc)
    else:
        # If target user does not exist, create it from scratch
        if not db.users.find_one({"_id": TARGET_USER}):
            print(f"   -> No source user found to copy. Creating {TARGET_USER} from scratch.")
            db.users.insert_one({
                "_id": TARGET_USER,
                "name": "Aryan (WhatsApp Demo)",
                "telegram_chat_id": None,
                "income": 50000.0,
                "currency": "INR",
                "created_at": datetime.datetime.utcnow(),
                "allocations": {
                    "Housing": 15000,
                    "Food & Dining": 8000,
                    "Transport": 4000,
                    "Utilities": 3000,
                    "Shopping": 5000,
                    "Groceries": 5000,
                    "Entertainment": 2000,
                    "Investment": 8000
                }
            })

    print(f"3. Reading CSV from {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    
    transactions = []
    
    # 80C injection for UI flexing
    transactions.append({
        "_id": str(uuid.uuid4()),
        "user_id": TARGET_USER,
        "date": (datetime.datetime.utcnow() - timedelta(days=20)),
        "amount": 25000.0,
        "description": "Quant ELSS Tax Saver Fund",
        "type": "debit",
        "category": "Investment",
        "method": "llm",
        "confidence": 0.99,
        "created_at": datetime.datetime.utcnow()
    })
    transactions.append({
        "_id": str(uuid.uuid4()),
        "user_id": TARGET_USER,
        "date": (datetime.datetime.utcnow() - timedelta(days=40)),
        "amount": 40000.0,
        "description": "PPF Deposit SBI Post Office",
        "type": "debit",
        "category": "Investment",
        "method": "llm",
        "confidence": 0.99,
        "created_at": datetime.datetime.utcnow()
    })

    for _, row in df.iterrows():
        try:
            raw_date = str(row['Date'])
            dt = datetime.datetime.strptime(raw_date, "%d-%m-%Y")
        except:
            dt = datetime.datetime.utcnow()

        amount = float(row['Amount'])
        desc = str(row['Description'])
        t_type = "credit" if "credit" in str(row['Type']).lower() else "debit"
        cat = get_logical_category(desc)

        transactions.append({
            "_id": str(uuid.uuid4()),
            "user_id": TARGET_USER,
            "date": dt,
            "amount": amount,
            "description": desc,
            "type": t_type,
            "category": cat,
            "method": "llm",
            "confidence": 0.95,
            "created_at": datetime.datetime.utcnow()
        })

    # Optional: Clear existing transactions for TARGET user before seeding this chunk to prevent duplicates?
    # db.transactions.delete_many({"user_id": TARGET_USER, "method": "llm"}) 
    # ^ No, they wanted MIGRATION, so we just append.
    
    print(f"4. Inserting {len(transactions)} perfect seed transactions...")
    db.transactions.insert_many(transactions)

    # If bills table is empty for TARGET_USER (meaning demo_user_001 had no bills), add some logical ones!
    if db.bills.count_documents({"user_id": TARGET_USER}) == 0:
        print("5. No bills migrated. Seeding fresh logical Bills...")
        bills = [
            {
                "_id": str(uuid.uuid4()),
                "user_id": TARGET_USER,
                "name": "Wi-Fi (Airtel Xstream)",
                "amount": 1100.0,
                "due_date": (datetime.datetime.utcnow() + timedelta(days=6)),
                "category": "Utilities",
                "status": "pending",
                "created_at": datetime.datetime.utcnow()
            },
            {
                "_id": str(uuid.uuid4()),
                "user_id": TARGET_USER,
                "name": "Apartment Rent",
                "amount": 15000.0,
                "due_date": (datetime.datetime.utcnow() + timedelta(days=15)),
                "category": "Housing",
                "status": "pending",
                "created_at": datetime.datetime.utcnow()
            }
        ]
        db.bills.insert_many(bills)

    # Same for goals
    if db.goals.count_documents({"user_id": TARGET_USER}) == 0:
        print("6. No goals migrated. Seeding fresh logical Goals...")
        goals = [
            {
                "_id": str(uuid.uuid4()),
                "user_id": TARGET_USER,
                "name": "Goa Trip Escrow Pool",
                "target_amount": 25000.0,
                "saved_amount": 15000.0,
                "target_date": (datetime.datetime.utcnow() + timedelta(days=30)),
                "category": "Travel",
                "status": "active",
                "blockchain_tracked": True,
                "created_at": datetime.datetime.utcnow()
            }
        ]
        db.goals.insert_many(goals)

    print("✅ Database perfectly seeded and migrated! Re-open dashboard on frontend.")

if __name__ == "__main__":
    seed()
