"""
Verify Tanuj -> Aryan Integration Flow
Tests the /transaction/add endpoint to ensure:
1. Auto-categorization works
2. Anomaly detection works (or fails gracefully)
3. Memory storage works
"""
import requests
import time

BASE_URL = "http://localhost:8000"
USER_ID = 999
HEADERS = {"Content-Type": "application/json"}

def test_transaction_flow():
    print("="*60)
    print("🧪 TESTING TRANSACTION INTEGRATION PIPELINE")
    print("="*60)
    
    # Test Case: Swiggy Order (Should be 'Food & Drink')
    payload = {
        "user_id": USER_ID,
        "description": "Swiggy food order",
        "amount": 450.0,
        "category": None  # Force auto-categorization
    }
    
    print("\n[TEST] Sending Transaction (Auto-categorize)...")
    try:
        start = time.time()
        resp = requests.post(f"{BASE_URL}/transaction/add", json=payload)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Success ({duration:.2f}s)")
            print(f"   Category: {data.get('category')} (Expected: Food & Drink)")
            print(f"   Anomaly:  {data.get('is_anomaly')}")
            print(f"   MemoryID: {data.get('memory_id')}")
            
            if data.get('category') == 'Food & Drink':
                print("   ✅ Categorization Verified")
            else:
                print(f"   ⚠️ Unexpected Category: {data.get('category')}")
                
            if data.get('memory_id'):
                print("   ✅ Memory Storage Verified")
        else:
            print(f"❌ Failed: {resp.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

    # Verify logic by asking Chatbot about it
    print("\n[TEST] Verifying Memory via Chat...")
    query_payload = {
        "user_id": USER_ID,
        "query": "How much did I spend on Swiggy recently?"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/chat", json=query_payload)
        if resp.status_code == 200:
            print(f"✅ Chat Response: {resp.json().get('response')}")
        else:
            print(f"❌ Chat Failed: {resp.text}")
    except:
        pass

    print("\n" + "="*60)

if __name__ == "__main__":
    test_transaction_flow()
