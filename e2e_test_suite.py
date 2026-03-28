"""
BudgetBandhu — Complete End-to-End Test Suite (ngrok edition)
Fixed version: correct response key names based on actual API output
"""
import requests, json, time, sys, tempfile, os
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────
RAG = "https://babylike-overtimorously-stacey.ngrok-free.dev"
ML  = "https://unoperated-merideth-sparklike.ngrok-free.dev"
FE  = "http://localhost:3000"
UID = "+91-9876543210"
SID = "test_e2e_001"
HDR = {"Content-Type": "application/json",
       "ngrok-skip-browser-warning": "true"}

results: dict = {}

# ─── HELPERS ────────────────────────────────────────────────────────────────
def h(t):    print(f"\n{'═'*62}\n  {t}\n{'═'*62}")
def sub(t):  print(f"\n  {'─'*58}\n  {t}")

def check(phase, label, ok, detail=""):
    sym = "✅ PASS" if ok else "❌ FAIL"
    results.setdefault(phase, []).append(ok)
    print(f"    {sym}  {label}")
    if detail and not ok:
        for ln in str(detail).splitlines()[:4]:
            print(f"           {ln}")
    return ok

def mem_has_count(m):
    for v in (m or {}).values():
        try:
            if int(str(v)) > 0: return True
        except: pass
    return False

def GET(path, base=RAG, timeout=20):
    try:
        r = requests.get(f"{base}{path}", headers=HDR, timeout=timeout)
        try:    body = r.json()
        except: body = {"_raw": r.text[:300]}
        return r.status_code, body
    except Exception as e:
        return 0, {"error": str(e)}

def POST(path, body, base=RAG, timeout=60):
    try:
        r = requests.post(f"{base}{path}", json=body, headers=HDR, timeout=timeout)
        try:    bd = r.json()
        except: bd = {"_raw": r.text[:300]}
        return r.status_code, bd
    except Exception as e:
        return 0, {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 1 — HEALTH CHECKS")

sub("TEST 1.1 — RAG Service Health")
c, d = GET("/health")
print(f"    {d}")
check("P1","RAG responds 200",         c == 200,           f"HTTP {c}")
check("P1","RAG status healthy",       d.get("status") in ("ok","healthy"), str(d))

sub("TEST 1.2 — ML Service Health")
c, d = GET("/ml/health", ML)
print(f"    {d}")
check("P1","ML responds 200",             c == 200,                             f"HTTP {c}")
check("P1","all_healthy=true",            d.get("all_healthy") is True,         str(d))
check("P1","categorizer_loaded",          d.get("categorizer_loaded") is True)
check("P1","anomaly_detector_loaded",     d.get("anomaly_detector_loaded") is True)
check("P1","forecaster_loaded",           d.get("forecaster_loaded") is True)
check("P1","policy_learner_loaded",       d.get("policy_learner_loaded") is True)

sub("TEST 1.3 — MongoDB Connection")
c, d = GET("/api/v1/health/db", timeout=35)
print(f"    {d}")
check("P1","DB endpoint responds",     c == 200,               f"HTTP {c}")
check("P1","MongoDB connected",        d.get("mongodb") == "connected", str(d))
check("P1","Collections present",      len(d.get("collections",[])) > 0)

sub("TEST 1.4 — Frontend Running")
try:
    r = requests.get(FE, timeout=6)
    check("P1","Frontend HTTP 200",       r.status_code == 200, f"HTTP {r.status_code}")
    check("P1","Page contains app name",  "budget" in r.text.lower() or "BudgetBandhu" in r.text)
except Exception as e:
    check("P1","Frontend reachable",      False, str(e))


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — ML SERVICE ROUTES
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 2 — ML SERVICE ROUTES")

sub("TEST 2.1 — Categorizer")
c, d = POST("/ml/categorize", {
    "descriptions": [
        "Swiggy Food Delivery", "Apollo Pharmacy", "Delhi Metro DMRC",
        "BigBasket BB Order", "Netflix India Subscription",
        "Zerodha Trading App", "Jio Recharge RJILPrepaid",
        "MakeMyTrip Hotel", "Unacademy Learn Subscription", "SBI ATM Withdrawal"
    ]
}, ML)
print(f"    HTTP {c}")
expected = [
    ("Swiggy Food Delivery",        ["food","dining"],                    0.85),
    ("Apollo Pharmacy",             ["health","medical","pharma"],        0.85),
    ("Delhi Metro DMRC",            ["transport","transit"],              0.80),
    ("BigBasket BB Order",          ["grocer","food"],                    0.80),
    ("Netflix India Subscription",  ["entertain","stream"],               0.80),
    ("Zerodha Trading App",         ["invest","financ","trading","stock"],0.40),
    ("Jio Recharge RJILPrepaid",    ["util","bill","telecom","mobile"],   0.80),
    ("MakeMyTrip Hotel",            ["travel","hotel"],                   0.80),
    ("Unacademy Learn",             ["educ","learn"],                     0.75),
    ("SBI ATM Withdrawal",          ["transfer","atm","cash","withdraw"], 0.65),
]
items = d if isinstance(d, list) else d.get("results", d.get("categories", []))
print(f"    Items returned: {len(items)}")
if items: print(f"    Sample: {items[0]}")
for i, (desc, cats, min_conf) in enumerate(expected):
    if i < len(items):
        it   = items[i]
        cat  = (it.get("category") or it.get("predicted_category","")).lower()
        conf = float(it.get("confidence", it.get("score", 0)))
        ok   = any(c2 in cat for c2 in cats) and conf >= min_conf
        check("P2", f"{desc[:24]:<25}→ {cat:<22} conf={conf:.2f}",
              ok, f"Expected one of {cats}")
    else:
        check("P2", f"{desc[:24]} result present", False, "missing from response")

sub("TEST 2.2 — Anomaly Detector")
c, d = POST("/ml/anomalies", {
    "transactions": [
        {"transaction_id":"t1","date":"2026-03-28","description":"Swiggy Food Delivery",
         "amount":150000,"transaction_type":"Debit","balance":0,"category":"Food & Dining"},
        {"transaction_id":"t2","date":"2026-03-28","description":"Uber India Trip",
         "amount":250,"transaction_type":"Debit","balance":0,"category":"Transport"},
    ],
    "history": []
}, ML)
print(f"    HTTP {c}")
print(f"    Response: {json.dumps(d, indent=2)[:600]}")
# FIXED: actual key is "anomalies" not "results"
items = d if isinstance(d, list) else d.get("anomalies", d.get("results", []))
a1 = items[0] if len(items) > 0 else {}
a2 = items[1] if len(items) > 1 else {}
sev1 = str(a1.get("severity", a1.get("anomaly_severity",""))).upper()
check("P2","₹1.5L Swiggy is_anomaly=true",  a1.get("is_anomaly") is True,           str(a1))
check("P2","₹1.5L Swiggy severity=HIGH",    "HIGH" in sev1,                         f"severity='{sev1}'")
check("P2","₹250 Uber not HIGH anomaly",
      not a2.get("is_anomaly") or "HIGH" not in str(a2.get("severity","")).upper(),  str(a2))

sub("TEST 2.3 — Forecaster")
c, d = POST("/ml/forecast", {
    "user_id": UID,
    "daily_history": [
        {"date": "2026-03-01", "category_amounts": {"Food & Dining": 350, "Income": 50000}},
        {"date": "2026-03-02", "category_amounts": {"Transport": 200}},
        {"date": "2026-03-03", "category_amounts": {"Groceries": 1200}},
        {"date": "2026-03-04", "category_amounts": {"Entertainment": 649}},
        {"date": "2026-03-05", "category_amounts": {"Utilities & Bills": 299}},
        {"date": "2026-03-06", "category_amounts": {"Groceries": 800}}
    ],
    "days_ahead": 7
}, ML)
print(f"    HTTP {c}")
print(f"    Keys: {list(d.keys()) if isinstance(d, dict) else type(d)}")
print(f"    Full response: {json.dumps(d, indent=2)[:500]}")
check("P2","Forecast responds 200",       c == 200, f"HTTP {c}")

# FIXED: actual keys are total_predicted_7d / forecast_by_day / confidence
predicted = (d.get("predicted_spending")
             or d.get("total_predicted_7d")
             or d.get("total_predicted_30d", 0))
check("P2","predicted_spending/total > 0",  float(predicted or 0) > 0,
      f"predicted={predicted}")

conf = float(d.get("confidence", 0))
check("P2","confidence 0-1",              0 <= conf <= 1.0, str(conf))

# FIXED: actual key is forecast_by_day, not forecast_7d
forecast_arr = (d.get("forecast_7d")
                or d.get("forecast_by_day")
                or d.get("daily_forecast", []))
check("P2","forecast array has ≥7 items", len(forecast_arr) >= 7,
      f"count={len(forecast_arr)}, key used=forecast_by_day")

sub("TEST 2.4 — Goal ETA")
c, d = POST("/ml/goal-eta", {
    "goal": {
        "name": "Europe Trip", "target_amount": 200000,
        "current_amount": 45000, "category": "Travel",
        "target_date": "2027-06-01", "priority": "High", "notes": ""
    },
    "transactions": [
        {"amount":50000,"category":"Income","transaction_type":"Credit","date":"2026-03-01"},
        {"amount":28000,"category":"Expenses","transaction_type":"Debit","date":"2026-03-15"}
    ]
}, ML)
print(f"    HTTP {c}")
print(f"    Response: {json.dumps(d, indent=2)[:500]}")
check("P2","Goal ETA responds 200",                c == 200, f"HTTP {c}")
check("P2","eta_days > 0",                         d.get("eta_days",0) > 0, str(d.get("eta_days")))
check("P2","projected_completion_date present",    bool(d.get("projected_completion_date")))
check("P2","on_track is bool",                     isinstance(d.get("on_track"), bool))


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 — CHAT / RAG PIPELINE
# NOTE: These will FAIL until MongoDB SSL is fixed
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 3 — CHAT / RAG PIPELINE")

sub("TEST 3.1 — Transaction Intent  ('I spent 450 on Swiggy')")
c, d = POST("/api/v1/chat", {
    "user_id": UID, "query": "I spent 450 on Swiggy today",
    "session_id": SID, "session_context": {}
})
rt = d.get("response","")
print(f"    HTTP {c}  |  response: {rt[:300]}")
check("P3","200 OK",                    c == 200, f"HTTP {c}")
check("P3","Response mentions transaction",
      any(w in rt.lower() for w in ["recorded","saved","added","transaction","logged"]), rt[:200])
check("P3","Category is Food (not Other)",
      any(w in rt.lower() for w in ["food","dining","swiggy"]), rt[:200])

sub("TEST 3.2 — Anomaly via Chat  ('I spent 1 lakh on Swiggy')")
c, d = POST("/api/v1/chat", {
    "user_id": UID, "query": "I spent 1 lakh on Swiggy today",
    "session_id": SID, "session_context": {}
})
rt = d.get("response","")
print(f"    HTTP {c}  |  response: {rt[:350]}")
check("P3","200 OK",          c == 200, f"HTTP {c}")
check("P3","Anomaly mentioned",
      any(w in rt.lower() for w in ["anomaly","unusual","suspicious","alert","warning","flag"]), rt[:300])

sub("TEST 3.3 — Tax Slab Query (no hallucination)")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "What are the income tax slabs in India for FY 2025-26?",
    "session_id": SID, "session_context": {}
})
rt = d.get("response","")
print(f"    HTTP {c}  |  response: {rt[:500]}")
check("P3","200 OK",                    c == 200,  f"HTTP {c}")
check("P3","No dollar signs",           "$" not in rt, "$ found!")
check("P3","Mentions regime/slab/lakh",
      any(w in rt.lower() for w in ["regime","slab","lakh","00,000","tax","3,00"]), rt[:300])

sub("TEST 3.4 — Hinglish Query")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "Mera paisa kahan ja raha hai? Bahut zyada kharch ho raha hai",
    "session_id": SID, "session_context": {}
})
rt = d.get("response","")
print(f"    HTTP {c}  |  response: {rt[:300]}")
check("P3","200 OK, no crash",    c == 200,   f"HTTP {c}")
check("P3","Non-empty response",  len(rt) > 30, f"len={len(rt)}")

sub("TEST 3.5 — Budget Context Query")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "How am I doing with my budget this month?",
    "session_id": SID, "session_context": {}
})
rt  = d.get("response","")
mem = d.get("memory_used", d.get("context_used", {}))
print(f"    HTTP {c}  |  memory={mem}  |  response: {rt[:300]}")
check("P3","200 OK",             c == 200,   f"HTTP {c}")
check("P3","Non-empty response", len(rt) > 50, f"len={len(rt)}")
check("P3","Memory/context used", bool(mem) and mem_has_count(mem), str(mem))

sub("TEST 3.6 — Investment Advice (PPF vs ELSS)")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "Should I invest in PPF or ELSS? I want to save tax.",
    "session_id": SID, "session_context": {}
})
rt = d.get("response","")
print(f"    HTTP {c}  |  response: {rt[:400]}")
check("P3","200 OK",              c == 200,  f"HTTP {c}")
check("P3","Mentions 80C",        "80c" in rt.lower() or "80 c" in rt.lower(), rt[:200])
check("P3","Mentions PPF or ELSS","ppf" in rt.lower() or "elss" in rt.lower(), rt[:200])
check("P3","No dollar signs",     "$" not in rt, "$ found!")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 — TRANSACTION CRUD
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 4 — TRANSACTION CRUD & ML PIPELINE")

sub("TEST 4.1 — Manual Transaction Entry")
c, d = POST("/api/v1/transactions", {
    "user_id": UID, "description": "Zepto Quick Grocery",
    "amount": 850, "transaction_type": "Debit", "date": "2026-03-28"
})
print(f"    HTTP {c}")
print(f"    Response: {json.dumps(d, indent=2)[:500]}")
txn_id = d.get("transaction_id") or d.get("id") or d.get("_id")
cat    = d.get("category","")
check("P4","POST 200/201",              c in (200,201), f"HTTP {c}")
check("P4","transaction_id present",    bool(txn_id),   str(d))
check("P4",f"Category=Groceries (got '{cat}')",
      any(w in cat.lower() for w in ["groc","food","zepto"]), f"cat={cat}")
check("P4","is_anomaly=false",          d.get("is_anomaly") == False, str(d.get("is_anomaly")))

sub("TEST 4.2 — List Transactions")
c, d = GET(f"/api/v1/transactions/{UID}")
txns = d if isinstance(d, list) else d.get("transactions", [])
print(f"    HTTP {c}  |  count={len(txns)}")
if txns: print(f"    Keys: {list(txns[0].keys())}")
check("P4","200 OK",        c == 200,       f"HTTP {c}")
check("P4","Count > 0",     len(txns) > 0,  f"count={len(txns)}")
if txns:
    t = txns[0]
    check("P4","Has anomaly_severity",
          "anomaly_severity" in t or "severity" in t, str(list(t.keys())))
    check("P4","Has category field",  "category" in t, str(list(t.keys())))

sub("TEST 4.3 — Anomaly Filter")
c, d = GET(f"/api/v1/transactions/{UID}?anomalies_only=true")
txns = d if isinstance(d, list) else d.get("transactions", [])
print(f"    HTTP {c}  |  anomaly count={len(txns)}")
all_anom = all(t.get("is_anomaly", False) for t in txns) if txns else True
check("P4","200 OK",                     c == 200,    f"HTTP {c}")
check("P4","All returned are anomalies", all_anom,    "non-anomaly found in list")
check("P4","≥1 anomaly exists",          len(txns) > 0, f"count={len(txns)}")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5 — DASHBOARD & ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 5 — DASHBOARD & ANALYTICS")

sub("TEST 5.1 — Dashboard with Forecast")
c, d = GET(f"/api/v1/dashboard/{UID}", timeout=30)
forecast = d.get("forecast") or {}
print(f"    HTTP {c}  |  top keys: {list(d.keys())}")
print(f"    forecast keys: {list(forecast.keys()) if forecast else 'EMPTY'}")
check("P5","200 OK",                     c == 200, f"HTTP {c}")
check("P5","forecast not null/empty",    bool(forecast), "forecast is empty {}")

predicted = (forecast.get("predicted_spending")
             or forecast.get("total_predicted_7d")
             or forecast.get("total_predicted_30d", 0))
check("P5","predicted_spending > 0",     float(predicted or 0) > 0,
      f"predicted={predicted}")

forecast_arr = (forecast.get("forecast_7d")
                or forecast.get("forecast_by_day")
                or forecast.get("daily_forecast", []))
check("P5","forecast_7d/by_day ≥7 items", len(forecast_arr) >= 7,
      f"count={len(forecast_arr)}")
check("P5","category_breakdown present",  bool(d.get("category_breakdown")))

sub("TEST 5.2 — Analytics Insights")
c, d = GET(f"/api/v1/analytics/{UID}")
insights = d.get("insights", [])
weekly   = d.get("weekly_summary", {})
print(f"    HTTP {c}  |  insights={len(insights)}  |  weekly={weekly}")
if insights: print(f"    Sample: {json.dumps(insights[0], indent=2)[:200]}")
check("P5","200 OK",                  c == 200,        f"HTTP {c}")
check("P5","insights non-empty",      len(insights) > 0, f"count={len(insights)}")
if insights:
    i = insights[0]
    check("P5","insight has type+title",
          "type" in i and "title" in i, str(list(i.keys())))
check("P5","weekly_summary present",  bool(weekly), str(weekly))


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6 — GOALS & BUDGET
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 6 — GOALS & BUDGET")

sub("SETUP — Seed Goals for Test User")
goals_to_seed = [
    {"name": "Emergency Fund",  "target_amount": 150000, "current_amount": 67500,
     "target_date": "2026-12-01", "category": "Savings",  "priority": "High"},
    {"name": "Europe Trip",     "target_amount": 200000, "current_amount": 45000,
     "target_date": "2027-06-01", "category": "Travel",   "priority": "Medium"},
    {"name": "New Laptop",      "target_amount": 120000, "current_amount": 92000,
     "target_date": "2026-09-01", "category": "Purchase", "priority": "High"},
]
for g in goals_to_seed:
    g["user_id"] = UID
    sc, sd = POST("/api/v1/goals", g)
    print(f"    Seeded goal '{g['name']}': HTTP {sc}")

sub("TEST 6.1 — Goals with AI ETA")
c, d = GET(f"/api/v1/goals/{UID}")
goals = d if isinstance(d, list) else d.get("goals", [])
print(f"    HTTP {c}  |  count={len(goals)}")
if goals: print(f"    Sample goal: {json.dumps(goals[0], indent=2)[:500]}")
check("P6","200 OK",           c == 200,       f"HTTP {c}")
check("P6","Goals non-empty",  len(goals) > 0, f"count={len(goals)}")
if goals:
    g = goals[0]
    check("P6","eta_days > 0",
          bool(g.get("eta_days")) and g.get("eta_days",0) > 0, str(g.get("eta_days")))
    check("P6","on_track is bool",
          isinstance(g.get("on_track"), bool), str(g.get("on_track")))

sub("TEST 6.2 — Budget Recommendations (PolicyLearner)")
c, d = GET(f"/api/v1/budget/{UID}/recommend")
recs = d.get("recommendations", [])
print(f"    HTTP {c}  |  recs count={len(recs)}")
print(f"    Response: {json.dumps(d, indent=2)[:500]}")
check("P6","200 OK",           c == 200,       f"HTTP {c}")
check("P6","Recs non-empty",   len(recs) > 0,  f"count={len(recs)}")
if recs:
    r = recs[0]
    spend = (r.get("current_spend")
             or r.get("actual_spent")
             or r.get("current_allocation", 0))
    check("P6","current_spend != 0", spend > 0, f"spend={spend}")
check("P6","total_savings_potential > 0",
      d.get("total_savings_potential",0) > 0, str(d.get("total_savings_potential")))

sub("TEST 6.3 — Budget Feedback (PolicyLearner persistence)")
# First call recommend to get an episode count
_, d_before = GET(f"/api/v1/budget/{UID}/recommend")
eps_before = d_before.get("episodes_trained", 0)

c, d = POST(f"/api/v1/budget/rec_001/feedback", {
    "accepted": True,
    "category": "Shopping",
    "user_id": UID
})
print(f"    HTTP {c}  |  {json.dumps(d, indent=2)[:300]}")
check("P6","Feedback 200",         c == 200, f"HTTP {c}")
check("P6","Has message/status",   bool(d),  str(d))

# Verify episode count incremented
time.sleep(1)
_, d_after = GET(f"/api/v1/budget/{UID}/recommend")
eps_after = d_after.get("episodes_trained", 0)
check("P6","PolicyLearner episodes incremented",
      eps_after > eps_before, f"before={eps_before} after={eps_after}")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 7 — AI LITERACY HUB
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 7 — AI LITERACY HUB")

sub("TEST 7.1 — Personalized Lesson (Smart Budgeting)")
c, d = POST("/api/v1/literacy/lesson", {
    "user_id": UID, "topic": "Smart Budgeting",
    "difficulty": "beginner", "session_id": "lit_test_001"
})
print(f"    HTTP {c}")
lesson  = d.get("lesson", {}) or {}
quiz    = d.get("quiz", {})   or {}
content = lesson.get("content","")
kps     = lesson.get("key_points",[])
qs      = quiz.get("questions",[])
print(f"    lesson.title: {lesson.get('title','—')}")
print(f"    content[:200]: {content[:200]}")
print(f"    key_points: {len(kps)}  |  quiz questions: {len(qs)}")
check("P7","200 OK",                   c == 200,          f"HTTP {c}")
check("P7","lesson.title present",     bool(lesson.get("title")))
check("P7","content > 100 chars",      len(content) > 100, f"len={len(content)}")
check("P7","₹ symbol in content",      "₹" in content or "Rs" in content,
      "No rupee symbol found")
check("P7","key_points ≥ 3",          len(kps) >= 3,     f"count={len(kps)}")
check("P7","Quiz has ≥ 4 questions",   len(qs) >= 4,      f"count={len(qs)}")
if qs:
    q = qs[0]
    check("P7","Question has 4 options", len(q.get("options",[])) == 4, str(q))

sub("TEST 7.2 — Tax Lesson (No Hallucination Check)")
c, d = POST("/api/v1/literacy/lesson", {
    "user_id": UID, "topic": "Tax Planning",
    "difficulty": "intermediate", "session_id": "lit_test_002"
})
lesson  = d.get("lesson", {}) or {}
content = lesson.get("content","")
print(f"    HTTP {c}  |  content[:400]: {content[:400]}")
check("P7","200 OK",                    c == 200, f"HTTP {c}")
check("P7","Mentions 80C",              "80c" in content.lower(), content[:200])
check("P7","No dollar signs",           "$" not in content, "$ found!")
check("P7","Mentions 1,50,000 / 1.5L",
      any(s in content for s in ["1,50,000","1.5 lakh","150000","1.5L"]), content[:300])


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 8 — CSV UPLOAD
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 8 — CSV UPLOAD")

sub("TEST 8.1 — Bank Statement CSV")
csv_content = (
    "Date,Description,Amount,Type,Balance\n"
    "2026-03-01,Salary Credit NEFT INFOSYS LTD,50000,Credit,97000\n"
    "2026-03-02,Swiggy Food Delivery,350,Debit,96650\n"
    "2026-03-03,Delhi Metro DMRC,45,Debit,96605\n"
    "2026-03-04,Amazon Pay India,1299,Debit,95306\n"
    "2026-03-05,Apollo Pharmacy,580,Debit,94726\n"
    "2026-03-06,Netflix India Subscription,649,Debit,94077\n"
    "2026-03-07,Zepto Quick Grocery,920,Debit,93157\n"
    "2026-03-08,Uber India Trip,180,Debit,92977\n"
    "2026-03-09,Jio Recharge RJILPrepaid,299,Debit,92678\n"
    "2026-03-10,BigBasket BB Order,1450,Debit,91228\n"
)
with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
    f.write(csv_content)
    tmp = f.name
try:
    with open(tmp, "rb") as fh:
        r = requests.post(
            f"{RAG}/api/v1/transactions/upload-csv",
            headers={"ngrok-skip-browser-warning":"true"},
            files={"file": ("test.csv", fh, "text/csv")},
            params={"user_id": UID},
            timeout=30
        )
    c = r.status_code
    try:    d = r.json()
    except: d = {"_raw": r.text[:300]}
    print(f"    HTTP {c}  |  {json.dumps(d, indent=2)[:500]}")
    parsed = (d.get("transactions_parsed")
              or d.get("inserted_count")
              or d.get("total_processed")
              or len(d.get("transactions",[])))
    check("P8","Upload 200/201",           c in (200,201),        f"HTTP {c}")
    check("P8","Parsed ≥ 10 transactions", int(parsed or 0) >= 10, f"parsed={parsed}")
    others = [t for t in d.get("transactions",[]) if t.get("category","").lower() == "other"]
    check("P8","No 'Other' categories",    len(others) == 0,       f"'Other' count={len(others)}")
except Exception as e:
    check("P8","CSV upload no exception",  False, str(e))
finally:
    os.unlink(tmp)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 9 — MEMORY SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 9 — MEMORY SYSTEM")

sub("TEST 9.1a — Set Memory (Europe trip)")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "I am saving for a Europe trip, my goal is 2 lakhs",
    "session_id": "mem_test_001", "session_context": {}
})
print(f"    HTTP {c}  |  {d.get('response','')[:150]}")
check("P9","Session-1 200", c == 200, f"HTTP {c}")

time.sleep(2)

sub("TEST 9.1b — Recall Memory (new session)")
c, d = POST("/api/v1/chat", {
    "user_id": UID,
    "query": "How am I progressing towards my travel goal?",
    "session_id": "mem_test_002", "session_context": {}
})
rt  = d.get("response","")
mem = d.get("memory_used", d.get("context_used", {}))
print(f"    HTTP {c}  |  memory={mem}")
print(f"    Response: {rt[:400]}")
check("P9","Session-2 200",     c == 200, f"HTTP {c}")
check("P9","Mentions Europe/travel/goal",
      any(w in rt.lower() for w in ["europe","travel","2 lakh","200000","goal"]), rt[:300])
check("P9","episodic/context count > 0",
      bool(mem) and mem_has_count(mem), str(mem))


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 11 — EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════
h("PHASE 11 — EDGE CASES")

sub("TEST 11.1 — Zero Amount")
c, d = POST("/api/v1/chat", {
    "user_id": UID, "query": "I spent 0 on swiggy",
    "session_id": "edge_001", "session_context": {}
})
print(f"    HTTP {c}  |  {d.get('response','')[:200]}")
check("P11","No crash (200 or 400)", c in (200,400), f"HTTP {c}")
check("P11","Not 500",               c != 500)

sub("TEST 11.2 — Huge Amount (₹99Cr)")
c, d = POST("/api/v1/chat", {
    "user_id": UID, "query": "I spent 99 crore on petrol",
    "session_id": "edge_002", "session_context": {}
})
print(f"    HTTP {c}  |  {d.get('response','')[:200]}")
check("P11","No crash (200)", c == 200, f"HTTP {c}")
check("P11","Not 500",        c != 500)

sub("TEST 11.3 — Unknown Merchant Categorize")
c, d = POST("/ml/categorize",
    {"descriptions": ["Ramu Kaka Chai Stall","XYZ Unknown Shop 1234"]}, ML)
print(f"    HTTP {c}  |  {d}")
check("P11","200 OK, no crash", c == 200, f"HTTP {c}")
check("P11","Returns results",  bool(d))

sub("TEST 11.4 — Chat with Empty Query")
c, d = POST("/api/v1/chat", {
    "user_id": UID, "query": "",
    "session_id": "edge_003", "session_context": {}
})
print(f"    HTTP {c}  |  {d}")
check("P11","Empty query doesn't 500", c != 500, f"HTTP {c}")

sub("TEST 11.5 — Invalid User ID")
c, d = GET("/api/v1/transactions/NONEXISTENT_USER_999")
print(f"    HTTP {c}  |  {d}")
check("P11","Invalid user returns 200 or 404", c in (200,404), f"HTTP {c}")
check("P11","Not 500",                         c != 500)


# ═══════════════════════════════════════════════════════════════════════════
# FINAL SCORECARD
# ═══════════════════════════════════════════════════════════════════════════
h("FINAL SCORECARD")
phase_names = {
    "P1":  "Phase 1   Health Checks          ",
    "P2":  "Phase 2   ML Service Routes      ",
    "P3":  "Phase 3   Chat / RAG Pipeline    ",
    "P4":  "Phase 4   Transaction CRUD + ML  ",
    "P5":  "Phase 5   Dashboard & Analytics  ",
    "P6":  "Phase 6   Goals & Budget         ",
    "P7":  "Phase 7   AI Literacy Hub        ",
    "P8":  "Phase 8   CSV Upload             ",
    "P9":  "Phase 9   Memory System          ",
    "P11": "Phase 11  Edge Cases             ",
}
critical = {"P1","P2","P3","P4","P5","P6"}
demo_ready = True

print()
for k, label in phase_names.items():
    checks   = results.get(k, [])
    if not checks:
        row     = "⚪ NOT RUN"
        ok_flag = False
    else:
        p, t    = sum(checks), len(checks)
        ok_flag = all(checks)
        row     = f"{'✅ PASS' if ok_flag else '❌ FAIL'}  ({p}/{t} checks)"
    print(f"  {label}  {row}")
    if k in critical and not ok_flag:
        demo_ready = False

print()
print("─"*62)
total_checks = sum(len(v) for v in results.values())
total_pass   = sum(sum(v) for v in results.values())
print(f"  Total: {total_pass}/{total_checks} checks passed")
print()
if demo_ready:
    print("  🎉  DEMO READY — All critical phases (1–6) PASSED!")
else:
    failed_phases = [phase_names[k].strip() for k in critical
                     if not all(results.get(k, [False]))]
    print("  ⚠️   BLOCKERS FOUND — Fix before demo:")
    for fp in failed_phases:
        print(f"       ❌ {fp}")
print("─"*62)
print(f"  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
