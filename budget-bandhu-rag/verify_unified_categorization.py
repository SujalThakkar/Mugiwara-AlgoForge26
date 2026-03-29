import httpx
import asyncio
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def verify_upload():
    user_id = "917558497556"
    csv_path = r"E:\PICT Techfiesta\BudgetBandhu\budget-bandhu-frontend\demo_transactions.csv"
    url = f"http://localhost:8000/api/v1/transactions/upload-csv?user_id={user_id}"

    print(f"🚀 [TEST] Uploading CSV to {url}...")
    
    with open(csv_path, "rb") as f:
        files = {"file": ("demo_transactions.csv", f, "text/csv")}
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(url, files=files)
            if r.status_code != 200:
                print(f"❌ Upload failed: {r.status_code} - {r.text}")
                return
            
            result = r.json()
            print(f"✅ Upload success! ML Summary: {result.get('ml_summary')}")

    # 2. Check Database for persistence
    print("🔍 [DB] Checking for persistent categorization in MongoDB...")
    client = AsyncIOMotorClient(os.getenv('MONGODB_ATLAS_URI'), tlsCAFile=certifi.where())
    db = client[os.getenv('MONGODB_DATABASE', 'budget_bandhu')]
    
    # Look for a specific record we know exists in demo_transactions.csv
    # e.g., 'Swiggy' or 'Starbucks'
    txn = await db['transactions'].find_one({"user_id": user_id, "description": {"$regex": "Swiggy", "$options": "i"}})
    
    if txn:
        print(f"✅ Found persisted transaction!")
        print(f"   - Description: {txn.get('description')}")
        print(f"   - Category: {txn.get('category')} (Method: {txn.get('categorization_method')})")
        print(f"   - Anomaly: {txn.get('is_anomaly')} (Severity: {txn.get('anomaly_severity')})")
        print(f"   - Confidence: {txn.get('category_confidence')}")
    else:
        print("❌ Could not find the transaction in DB. Persistence failed.")

    client.close()

if __name__ == '__main__':
    asyncio.run(verify_upload())
