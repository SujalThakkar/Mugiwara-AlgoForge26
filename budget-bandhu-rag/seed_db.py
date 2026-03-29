import pandas as pd
from pymongo import MongoClient
import uuid
import datetime
from datetime import timedelta

# ── CONFIG ──
ATLAS_URI = "mongodb+srv://aryanlomte_db_user:1o1s26Syatgt2b5R@cluster0.0mw7kni.mongodb.net/?appName=Cluster0"
DB_NAME = "budget_bandhu"
USER_ID = "917558497556"
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
    elif any(k in desc for k in ['bill', 'electricity', 'bescom', 'tata power', 'broadband', 'recharge', 'jio']):
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

    print("Wiping all existing Demo/Test data EXCEPT user-demo...")
    filter_query = {"user_id": {"$ne": "user-demo"}}
    
    # Standard Collections
    for coll in ["users", "transactions", "bills", "goals"]:
        col = db[coll]
        if coll == "users":
            col.delete_many({"_id": {"$ne": "user-demo"}})
        else:
            col.delete_many(filter_query)

    # Agent Memory Collections
    for coll in ["agent_episodic_memory", "agent_semantic_memory", "agent_procedural_memory", "agent_working_memory", "agent_trajectory_memory", "knowledge_graph"]:
        col = db[coll]
        col.delete_many(filter_query)

    print(f"Creating user {USER_ID}...")
    db.users.insert_one({
        "_id": USER_ID,
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

    print(f"Reading CSV from {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    
    transactions = []
    # Seed 80C UI Transactions
    transactions.append({
        "_id": str(uuid.uuid4()),
        "user_id": USER_ID,
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
        "user_id": USER_ID,
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
            "user_id": USER_ID,
            "date": dt,
            "amount": amount,
            "description": desc,
            "type": t_type,
            "category": cat,
            "method": "llm",
            "confidence": 0.95,
            "created_at": datetime.datetime.utcnow()
        })

    print(f"Inserting {len(transactions)} transactions...")
    db.transactions.insert_many(transactions)

    print("Seeding Bills...")
    bills = [
        {
            "_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "name": "Wi-Fi (Airtel Xstream)",
            "amount": 1100.0,
            "due_date": (datetime.datetime.utcnow() + timedelta(days=6)),
            "category": "Utilities",
            "status": "pending",
            "created_at": datetime.datetime.utcnow()
        },
        {
            "_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "name": "Apartment Rent",
            "amount": 15000.0,
            "due_date": (datetime.datetime.utcnow() + timedelta(days=15)),
            "category": "Housing",
            "status": "pending",
            "created_at": datetime.datetime.utcnow()
        },
        {
            "_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "name": "Car EMI",
            "amount": 4500.0,
            "due_date": (datetime.datetime.utcnow() - timedelta(days=2)), # Overdue example
            "category": "Transport",
            "status": "pending",
            "created_at": datetime.datetime.utcnow()
        }
    ]
    db.bills.insert_many(bills)

    print("Seeding Goals...")
    goals = [
        {
            "_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "name": "Goa Trip Escrow Pool",
            "target_amount": 25000.0,
            "saved_amount": 15000.0,
            "target_date": (datetime.datetime.utcnow() + timedelta(days=30)),
            "category": "Travel",
            "status": "active",
            "blockchain_tracked": True,
            "created_at": datetime.datetime.utcnow()
        },
        {
            "_id": str(uuid.uuid4()),
            "user_id": USER_ID,
            "name": "Emergency Fund",
            "target_amount": 100000.0,
            "saved_amount": 80000.0,
            "target_date": (datetime.datetime.utcnow() + timedelta(days=120)),
            "category": "Savings",
            "status": "active",
            "blockchain_tracked": False,
            "created_at": datetime.datetime.utcnow()
        }
    ]
    db.goals.insert_many(goals)
    
    print("✅ Database perfectly seeded!")

if __name__ == "__main__":
    seed()
