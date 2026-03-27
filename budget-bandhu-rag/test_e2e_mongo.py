"""
End-to-End Test: Budget Bandhu (MongoDB Architecture)
Simulates a full user journey using Mobile Number as ID.
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"
USER_MOBILE = "9876543210"  # Test Mobile Number
HEADERS = {"Content-Type": "application/json"}

def log_section(title):
    print("\n" + "="*80)
    print(f"🔹 {title}")
    print("="*80)

def log_exchange(step, endpoint, payload, response_data, duration):
    print(f"\n🔸 STEP {step}: {endpoint}")
    print(f"   ⏱️ Duration: {duration:.3f}s")
    print("\n   📤 INPUT (Request):")
    print(json.dumps(payload, indent=2))
    print("\n   📥 OUTPUT (Response):")
    print(json.dumps(response_data, indent=2))

def run_test():
    print(f"🚀 STARTING END-TO-END TEST FOR USER: {USER_MOBILE}")
    
    # ====================================================================
    # STEP 1: SET USER PROFILE (SEMANTIC MEMORY)
    # ====================================================================
    log_section("PHASE 1: ONBOARDING (SEMANTIC MEMORY)")
    
    endpoint = "/memory/semantic"
    payload = {
        "user_id": USER_MOBILE,
        "attribute_type": "monthly_income",
        "value": "₹1,20,000"
    }
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}{endpoint}", json=payload)
    log_exchange(1, endpoint, payload, resp.json(), time.time() - start)
    
    # ====================================================================
    # STEP 2: ADD TRANSACTION (CATEGORIZATION + ANOMALY + STORAGE)
    # ====================================================================
    log_section("PHASE 2: TRANSACTION FLOW (ML + MEMORY)")
    
    endpoint = "/transaction/add"
    payload = {
        "user_id": USER_MOBILE,
        "description": "Dinner at Mainland China",
        "amount": 4500.0,
        "category": None  # Expect auto-categorization
    }
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}{endpoint}", json=payload)
    log_exchange(2, endpoint, payload, resp.json(), time.time() - start)
    
    # Store memory ID for later verification if needed
    
    # ====================================================================
    # STEP 3: ANALYTICS (INSIGHTS)
    # ====================================================================
    log_section("PHASE 3: ANALYTICS (INSIGHTS)")
    
    endpoint = f"/analytics/{USER_MOBILE}"
    
    start = time.time()
    resp = requests.get(f"{BASE_URL}{endpoint}")
    log_exchange(3, endpoint, {}, resp.json(), time.time() - start)
    
    # ====================================================================
    # STEP 4: RAG CHAT (MEMORY RETRIEVAL + CONVERSATION)
    # ====================================================================
    log_section("PHASE 4: AGENTIC CHAT (RAG)")
    
    # Turn 1: Ask about spending
    endpoint = "/chat"
    payload = {
        "user_id": USER_MOBILE,
        "query": "How much did I spend on dinner recently?"
    }
    
    start = time.time()
    resp = requests.post(f"{BASE_URL}{endpoint}", json=payload)
    data = resp.json()
    log_exchange(4, endpoint + " (Turn 1)", payload, data, time.time() - start)
    
    session_id = data.get("session_id")
    
    # Turn 2: Follow up (Context)
    if session_id:
        payload = {
            "user_id": USER_MOBILE,
            "query": "Is that expensive given my income?",
            "session_id": session_id
        }
        
        start = time.time()
        resp = requests.post(f"{BASE_URL}{endpoint}", json=payload)
        log_exchange(5, endpoint + " (Turn 2)", payload, resp.json(), time.time() - start)

    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    try:
        # Simple health check retry loop
        for i in range(5):
            try:
                requests.get(f"{BASE_URL}/health")
                break
            except:
                time.sleep(1)
                
        run_test()
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        print("Make sure the server is running!")
