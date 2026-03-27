"""
Verify Agentic Conversational Logic
Tests the full RAG pipeline via the running API.
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"
USER_ID = 999  # Test user
HEADERS = {"Content-Type": "application/json"}

def test_chat():
    print("="*60)
    print("🤖 TESTING AGENTIC CONVERSATIONAL LOGIC")
    print("="*60)
    
    # 1. Store Semantic Memory (Income)
    print("\n[TEST] 1. Storing Income Memory...")
    req_data = {
        "user_id": USER_ID,
        "attribute_type": "monthly_income",
        "value": "₹85,000"
    }
    resp = requests.post(f"{BASE_URL}/memory/semantic", json=req_data)
    if resp.status_code == 200:
        print("✅ Memory Stored")
    else:
        print(f"❌ Failed to store memory: {resp.text}")
        return

    # 2. Chat Turn 1: Grounded Question
    print("\n[TEST] 2. Chat Turn 1: 'What is my monthly income?'")
    query = "What is my monthly income?"
    req_data = {
        "user_id": USER_ID, 
        "query": query
    }
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}/chat", json=req_data)
    duration = time.time() - start
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Response ({duration:.2f}s):")
        print(f"   > {data['response']}")
        print(f"   Confidence: {data.get('confidence')}")
        session_id = data.get('session_id')
        
        if "85,000" in data['response']:
            print("   ✅ CORRECT: Retrieved semantic memory")
        else:
            print("   ❌ FAILURE: Did not retrieve memory")
            
    else:
        print(f"❌ Chat failed: {resp.text}")
        return

    # 3. Chat Turn 2: Conversational Follow-up (Context)
    print(f"\n[TEST] 3. Chat Turn 2: 'What is 10% of that?' (Session: {session_id})")
    query = "What is 10% of that for savings?"
    req_data = {
        "user_id": USER_ID, 
        "query": query,
        "session_id": session_id
    }
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}/chat", json=req_data)
    duration = time.time() - start
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Response ({duration:.2f}s):")
        print(f"   > {data['response']}")
        
        # We expect it to calculate 8,500 or refer to the income
        if "8,500" in data['response'] or "8500" in data['response']:
            print("   ✅ CORRECT: Maintained conversational context")
        elif "85,000" in data['response']:
            print("   ⚠️ PARTIAL: Mentioned income but maybe not calculation")
        else:
            print("   ❌ FAILURE: Lost context most likely")
            
    else:
        print(f"❌ Chat failed: {resp.text}")

    print("\n" + "="*60)
    print("🏁 TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    try:
        # Wait a sec for server to be fully ready if it just started
        time.sleep(2) 
        test_chat()
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server at http://localhost:8000")
        print("   Make sure app.py is running!")
