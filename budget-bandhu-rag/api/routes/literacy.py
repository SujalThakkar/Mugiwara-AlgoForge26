"""AI Literacy Hub - Personalized financial lessons via Phi-3.5 RAG."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from collections import defaultdict
import json, re, logging, uuid
import requests as http_requests
from api.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/literacy", tags=["Literacy"])
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "budget-bandhu"


class LessonRequest(BaseModel):
    user_id: str
    topic: str
    difficulty: str = "beginner"
    session_id: str = ""


class QuizResultRequest(BaseModel):
    user_id: str
    session_id: str
    score: int
    total: int


async def _build_user_context(db, user_id):
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    cursor = db["transactions"].find({"user_id": user_id, "type": "debit", "created_at": {"$gte": thirty_days_ago}})
    txns = await cursor.to_list(length=500)
    user = await db["users"].find_one({"_id": user_id})
    income = user.get("income", 50000) if user else 50000
    cat_spend = defaultdict(float)
    total = 0.0
    for t in txns:
        cat_spend[t.get("category", "Other")] += t.get("amount", 0)
        total += t.get("amount", 0)
    top3 = sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)[:3]
    rate = max(0, round((income - total) / income * 100, 1)) if income > 0 else 0
    budget = await db["budgets"].find_one({"user_id": user_id})
    overspent = []
    budget_health = 100
    if budget:
        total_alloc = sum(a.get("allocated", 0) for a in budget.get("allocations", []))
        budget_health = round(total / total_alloc * 100, 1) if total_alloc > 0 else 100
        for alloc in budget.get("allocations", []):
            if cat_spend.get(alloc["category"], 0) > alloc.get("allocated", 0):
                overspent.append(alloc["category"])
    return {"income": income, "total_spend": total, "top_cats": top3, "savings_rate": rate,
            "overspent": overspent, "budget_health": budget_health, "category_spend": dict(cat_spend)}


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _fallback_lesson(topic, ctx):
    top_cat = ctx["top_cats"][0][0] if ctx["top_cats"] else "general expenses"
    top_amt = ctx["top_cats"][0][1] if ctx["top_cats"] else 0

    # ── Topic-specific content ──────────────────────────────────────────────
    topic_lower = topic.lower()

    if "tax" in topic_lower:
        content = (
            f"Tax Planning for FY 2025-26: Under Section 80C you can claim deductions up to "
            f"₹1,50,000 per year. Best 80C instruments: PPF (Public Provident Fund) — "
            f"safe, 7.1% p.a., 15-year lock-in; ELSS mutual funds — market-linked, 3-year "
            f"lock-in, historically 12-15% returns. Compare new vs old tax regime: new regime "
            f"has lower rates but no 80C/HRA deductions. If your deductions exceed ₹3.75 lakh, "
            f"old regime is better. Your current spend: ₹{ctx['total_spend']:,.0f}. "
            f"Savings rate: {ctx['savings_rate']}%."
        )
        key_points = [
            "Section 80C limit: ₹1,50,000 per year",
            "PPF: safe 7.1% p.a. — ELSS: market-linked 3yr lock-in",
            "Compare new vs old tax regime before filing ITR",
        ]
        quiz_questions = [
            {"q": "What is the Section 80C annual deduction limit?",
             "options": ["₹50,000", "₹1,00,000", "₹1,50,000", "₹2,00,000"],
             "correct": 2, "explanation": "₹1,50,000 is the 80C limit."},
            {"q": "What is the lock-in period for ELSS funds?",
             "options": ["1 year", "3 years", "5 years", "15 years"],
             "correct": 1, "explanation": "ELSS has a 3-year lock-in."},
            {"q": "PPF interest rate (approx)?",
             "options": ["5%", "6%", "7.1%", "9%"],
             "correct": 2, "explanation": "PPF gives ~7.1% p.a."},
            {"q": "New tax regime differs because it:",
             "options": ["Has higher slabs", "Removes 80C/HRA deductions", "Applies only to seniors", "Is mandatory"],
             "correct": 1, "explanation": "New regime removes most exemptions including 80C."},
        ]
        personalized = f"Invest ₹1,50,000 in ELSS/PPF to save up to ₹46,800 in taxes (30% slab)."

    elif any(w in topic_lower for w in ["invest", "ppf", "elss", "mutual", "sip"]):
        content = (
            f"Investment Basics: Start with SIPs in index funds or ELSS. PPF (Section 80C) "
            f"gives safe ₹1,50,000 deduction. ELSS gives higher returns with 3-yr lock-in. "
            f"Your income: ₹{ctx['income']:,.0f}/month. Top spend: {top_cat} ₹{top_amt:,.0f}. "
            f"Target 20% savings rate. Current: {ctx['savings_rate']}%."
        )
        key_points = [
            "SIP in index funds — start with ₹500/month",
            "PPF + ELSS cover Section 80C ₹1,50,000 limit",
            "Emergency fund first, then invest surplus",
        ]
        quiz_questions = [
            {"q": "PPF lock-in period?", "options": ["3 yr", "5 yr", "15 yr", "10 yr"], "correct": 2, "explanation": "PPF is 15 years."},
            {"q": "ELSS lock-in?", "options": ["1 yr", "3 yr", "5 yr", "7 yr"], "correct": 1, "explanation": "ELSS is 3 years."},
            {"q": "80C limit?", "options": ["₹50k", "₹1L", "₹1.5L", "₹2L"], "correct": 2, "explanation": "₹1,50,000."},
            {"q": "SIP benefits?", "options": ["Lump-sum only", "Rupee cost averaging", "Guaranteed return", "No risk"], "correct": 1, "explanation": "SIPs average purchase cost over time."},
        ]
        personalized = f"Max out 80C with ELSS: invest ₹12,500/month to hit ₹1,50,000 limit."

    else:
        # Generic smart budgeting fallback
        content = (
            f"Understanding finances is key. This month you spent ₹{ctx['total_spend']:,.0f}. "
            f"Top category: {top_cat} ₹{top_amt:,.0f}. "
            f"Target 20% savings rate. Current: {ctx['savings_rate']}%. "
            f"Apply 50-30-20 rule: 50% needs, 30% wants, 20% savings."
        )
        key_points = ["Track every expense", "Aim for 20% savings", "Review weekly"]
        quiz_questions = [
            {"q": "Recommended savings rate?", "options": ["5%", "10%", "20%", "50%"], "correct": 2, "explanation": "20% is recommended."},
            {"q": "Your top category?", "options": [top_cat, "Travel", "Rent", "Other"], "correct": 0, "explanation": top_cat + " is highest."},
            {"q": "50/30/20 rule is?", "options": ["Tax", "Budget", "Investment", "Loan"], "correct": 1, "explanation": "50% needs, 30% wants, 20% savings."},
            {"q": "Review spending how often?", "options": ["Yearly", "Monthly", "Weekly", "Never"], "correct": 2, "explanation": "Weekly helps catch overspend."},
        ]
        personalized = f"Top spend: {top_cat} ₹{top_amt:,.0f}."

    return {
        "lesson": {
            "title": topic + ": Getting Started",
            "content": content,
            "key_points": key_points,
            "personalized_example": personalized,
            "estimated_minutes": 10,
        },
        "quiz": {"questions": quiz_questions}
    }


@router.post("/lesson")
async def generate_lesson(req: LessonRequest, db=Depends(get_database)):
    """Generate a personalized financial literacy lesson with quiz using Phi-3.5."""
    try:
        ctx = await _build_user_context(db, req.user_id)
        top_str = ", ".join("{} Rs{:,.0f}".format(c[0], c[1]) for c in ctx["top_cats"]) or "N/A"
        overspent_str = ", ".join(ctx["overspent"]) or "None"
        sid = req.session_id or str(uuid.uuid4())

        # Build topic-specific prompt
        topic_context = {
            "Smart Budgeting": "50-30-20 rule, emergency fund, avoiding Swiggy/Zomato overspend, UPI tracking",
            "Tax Planning":    "Section 80C (₹1,50,000 limit), PPF, ELSS, 80D health insurance, new vs old regime, ITR filing",
            "Investment Basics": "SIP, mutual funds, index funds, Zerodha/Groww, ELSS 3yr lock-in",
            "Savings Strategy": "Emergency fund (3-6 months), liquid funds, recurring deposits",
            "Debt Management": "EMI management, credit card 42% interest, CIBIL score",
            "Financial Goals": "SMART goals, SIP for goals, goal-based investing"
        }.get(req.topic, req.topic)
        
        # Build prompt
        p = []
        p.append("You are BudgetBandhu financial literacy coach.")
        p.append(f"Generate a personalized {req.difficulty} lesson on \"{req.topic}\" for an Indian earner.")
        p.append(f"Key concepts to cover: {topic_context}")
        p.append("")
        p.append("USER REAL FINANCIAL DATA:")
        p.append(f"- Monthly income: ₹{ctx['income']:,.0f}")
        p.append(f"- Top spending: {top_str}")
        p.append(f"- Savings rate: {ctx['savings_rate']}%")
        p.append(f"- Overspent: {overspent_str}")
        p.append(f"- Budget health: {ctx['budget_health']}% used")
        p.append("")
        p.append("RULES:")
        p.append("1. Write a 150-200 word lesson referencing THEIR actual numbers")
        p.append("2. Give 3 key_points as bullets")
        p.append("3. Give 1 personalized_example using their real data")
        p.append("4. Create 4 quiz questions derived from their actual spending")
        p.append("CRITICAL: Use ₹ not $. Use Indian terms (lakh, crore). For Tax Planning, MUST mention Section 80C limit of ₹1,50,000.")
        p.append("")
        p.append("Respond ONLY in this exact JSON format:")
        schema = ('{"lesson":{"title":"...","content":"...","key_points":["...","...","..."],'
                  '"personalized_example":"...","estimated_minutes":15},'
                  '"quiz":{"questions":[{"q":"...","options":["...","...","...","..."],"correct":0,"explanation":"..."},'
                  '{"q":"...","options":["...","...","...","..."],"correct":1,"explanation":"..."},'
                  '{"q":"...","options":["...","...","...","..."],"correct":2,"explanation":"..."},'
                  '{"q":"...","options":["...","...","...","..."],"correct":3,"explanation":"..."}]}}')
        p.append(schema)
        prompt = "\n".join(p)

        # Call Ollama
        lesson_data = {}
        try:
            resp = http_requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.7, "num_predict": 1024}},
                timeout=60
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            lesson_data = _extract_json(raw)
        except Exception as e:
            logger.warning("[Literacy] Ollama call failed: {}".format(e))

        if not lesson_data.get('lesson'):
            lesson_data = _fallback_lesson(req.topic, ctx)

        # Save session to MongoDB
        try:
            await db["literacy_sessions"].insert_one({
                "session_id": sid,
                "user_id": req.user_id,
                "topic": req.topic,
                "difficulty": req.difficulty,
                "completed_at": datetime.utcnow(),
                "quiz_score": None,
                "lesson_title": lesson_data.get("lesson", {}).get("title", req.topic),
            })
        except Exception as e:
            logger.warning("[Literacy] Session save failed: {}".format(e))

        return {**lesson_data, "session_id": sid}

    except Exception as e:
        logger.error("[Literacy] Lesson error: {}".format(e))
        raise HTTPException(status_code=503, detail="AI lesson generation failed, try again")


@router.get("/history/{user_id}")
async def get_lesson_history(user_id: str, db=Depends(get_database)):
    """Returns last 10 completed literacy sessions for a user."""
    try:
        cursor = db["literacy_sessions"].find({"user_id": user_id}).sort("completed_at", -1).limit(10)
        sessions = await cursor.to_list(length=10)
        result = []
        for s in sessions:
            result.append({
                "session_id": s.get("session_id", str(s.get("_id", ""))),
                "topic": s.get("topic", ""),
                "difficulty": s.get("difficulty", "beginner"),
                "completed_at": s.get("completed_at", datetime.utcnow()).isoformat(),
                "quiz_score": s.get("quiz_score"),
                "lesson_title": s.get("lesson_title", ""),
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quiz-result")
async def save_quiz_result(req: QuizResultRequest, db=Depends(get_database)):
    """Save quiz score for a completed literacy session."""
    try:
        pct = round(req.score / max(req.total, 1) * 100, 1)
        await db["literacy_sessions"].update_one(
            {"session_id": req.session_id, "user_id": req.user_id},
            {"$set": {"quiz_score": req.score, "quiz_total": req.total, "quiz_pct": pct, "quiz_completed_at": datetime.utcnow()}},
            upsert=False,
        )
        return {"status": "ok", "score": req.score, "total": req.total, "percentage": pct}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
