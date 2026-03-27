import requests
import time
import json

BASE_URL = "http://localhost:8000"
USER_MOBILE = f"91{int(time.time())}" # Unique for this run

def log_step(name):
    print(f"\n{'='*20} STEP: {name} {'='*20}")

def run_orchestration_test():
    # 1. USER REGISTRATION
    log_step("User Registration")
    reg_payload = {
        "mobile": USER_MOBILE,
        "name": "Orchestration Tester",
        "income": 100000, # 1 Lakh income
        "password": "pass"
    }
    r = requests.post(f"{BASE_URL}/api/v1/user/register", json=reg_payload)
    if r.status_code != 200:
        print(f"[FAIL] Registration Failed: {r.status_code}")
        print(f"Detail: {r.text}")
        return
    print(f"[OK] User registered: {USER_MOBILE}")

    # 2. ADD TRANSACTIONS (Testing ML Pipeline)
    log_step("Add Transactions (ML Trigger)")
    # Normal transaction
    tx1 = {
        "date": "2026-01-17",
        "amount": 2500,
        "description": "Weekly grocery shopping at D-Mart",
        "type": "debit"
    }
    # Anomalous transaction (Huge spend)
    tx2 = {
        "date": "2026-01-17",
        "amount": 85000,
        "description": "Purchased Super Gaming PC with dual RTX 4090",
        "type": "debit"
    }

    print("Inserting normal txn...")
    r_tx1 = requests.post(f"{BASE_URL}/api/v1/transactions?user_id={USER_MOBILE}", json=tx1)
    if r_tx1.status_code != 200:
        print(f"[FAIL] Normal Txn Failed: {r_tx1.status_code} - {r_tx1.text}")
        return
    
    print("Inserting anomalous txn...")
    r2 = requests.post(f"{BASE_URL}/api/v1/transactions?user_id={USER_MOBILE}", json=tx2)
    if r2.status_code != 200:
        print(f"[FAIL] Anomalous Txn Failed: {r2.status_code} - {r2.text}")
        return
    res2 = r2.json()
    print(f"[OK] Processed Txn: Category={res2.get('category')}, Anomaly={res2.get('is_anomaly')}")
    
    # 3. CHAT ORCHESTRATION (Testing RAG + Memory)
    log_step("AI Agent Chat (Memory Retrieval)")
    chat_payload = {
        "user_id": USER_MOBILE,
        "query": "Which was my most expensive purchase today and why is it problematic?",
        "session_id": "orchestration-test"
    }
    print("Asking Agent...")
    r3 = requests.post(f"{BASE_URL}/api/v1/chat", json=chat_payload)
    if r3.status_code == 200:
        res3 = r3.json()
        print(f"Agent Response: {res3.get('response')}")
        print(f"Confidence: {res3.get('confidence')}")
        print(f"Memory Used: {res3.get('memory_used')}")
    else:
        print(f"[FAIL] Chat Failed: {r3.text}")

    # 4. ANALYTICS & INSIGHTS
    log_step("Analytics & Insights")
    r4 = requests.get(f"{BASE_URL}/api/v1/analytics/{USER_MOBILE}")
    if r4.status_code == 200:
        res4 = r4.json()
        print(f"Insights: {json.dumps(res4.get('insights', []), indent=2)}")
    else:
        print(f"[FAIL] Analytics Failed: {r4.text}")

    # 5. FORECASTING
    log_step("Expense Forecasting")
    forecast_payload = {"user_id": USER_MOBILE, "months": 3}
    r5 = requests.post(f"{BASE_URL}/api/v1/forecast", json=forecast_payload)
    if r5.status_code == 200:
        res5 = r5.json()
        print(f"Forecast: {res5.get('forecast')}")
    else:
        print(f"[FAIL] Forecast Failed: {r5.text}")

if __name__ == "__main__":
    time.sleep(1) # Wait for server
    try:
        run_orchestration_test()
    except Exception as e:
        print(f"[CRASH] Orchestration Test Crashed: {e}")
