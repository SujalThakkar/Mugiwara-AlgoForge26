from pymongo import MongoClient
import os

# To patch the user with a password
from api.routes.user import get_password_hash

ATLAS_URI = "mongodb+srv://aryanlomte_db_user:1o1s26Syatgt2b5R@cluster0.0mw7kni.mongodb.net/?appName=Cluster0"
DB_NAME = "budget_bandhu"

client = MongoClient(ATLAS_URI)
db = client[DB_NAME]

user_id = "917558497556"
hashed_pw = get_password_hash("budget123")

db.users.update_one({"_id": user_id}, {"$set": {"password_hash": hashed_pw}})
print(f"Successfully set password for {user_id} to 'budget123'")
