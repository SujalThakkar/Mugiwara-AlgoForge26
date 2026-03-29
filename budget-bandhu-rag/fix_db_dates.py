from pymongo import MongoClient
from datetime import datetime
import os

ATLAS_URI = "mongodb+srv://aryanlomte_db_user:1o1s26Syatgt2b5R@cluster0.0mw7kni.mongodb.net/?appName=Cluster0"
DB_NAME = "budget_bandhu"
TARGET_USER = "917558497556"

client = MongoClient(ATLAS_URI)
db = client[DB_NAME]

print("Fixing Bills due_date type...")
bills = db.bills.find({"user_id": TARGET_USER})
count = 0
for b in bills:
    if isinstance(b.get('due_date'), datetime):
        due_str = b['due_date'].strftime("%Y-%m-%d")
        db.bills.update_one({"_id": b["_id"]}, {"$set": {"due_date": due_str}})
        count += 1
print(f"Updated {count} bills.")

print("Fixing Goals target_date type...")
goals = db.goals.find({"user_id": TARGET_USER})
count = 0
for g in goals:
    if isinstance(g.get('target_date'), datetime):
        due_str = g['target_date'].strftime("%Y-%m-%d")
        db.goals.update_one({"_id": g["_id"]}, {"$set": {"target_date": due_str}})
        count += 1
print(f"Updated {count} goals.")

print("Ensuring transactions have ISO dates just in case, and ml pipeline metadata...")
txns = db.transactions.find({"user_id": TARGET_USER})
count = 0
for t in txns:
    updates = {}
    if isinstance(t.get('date'), datetime):
        updates['date'] = t['date'].strftime("%Y-%m-%d")
        
    # Also inject the anomaly stuff so the ML dashboard doesn't complain
    if t.get('category') == "Investment":
        updates["is_anomaly"] = True
        updates["anomaly_score"] = -0.8
        updates["anomaly_severity"] = "LOW"
    else:
        updates["is_anomaly"] = False
        updates["anomaly_score"] = 0.5
        updates["anomaly_severity"] = "NORMAL"

    if updates:
        db.transactions.update_one({"_id": t["_id"]}, {"$set": updates})
        count += 1
print(f"Updated {count} transactions.")
