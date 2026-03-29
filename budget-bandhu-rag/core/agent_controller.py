"""
core/agent_controller.py — Single source of truth for all chat logic.
"""
import logging, re, asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("BudgetBandhu")

# ── Canonical imports ────────────────────────────────────────
from intelligence.phi3_rag           import Phi3RAG
from intelligence.ml_client          import MLClient
from memory.conversation_manager     import ConversationManager
from memory.episodic_memory          import EpisodicMemoryStore
from memory.semantic_memory          import SemanticMemoryStore
from memory.working_memory           import WorkingMemoryStore
from memory.procedural_memory        import ProceduralMemoryStore
from memory.trajectory_memory        import TrajectoryMemoryStore
from memory.cognitive_memory_manager import CognitiveMemoryManager
from memory.knowledge_graph          import KnowledgeGraphStore
from database.mongo_manager          import MongoManager
from core.gating                     import GatingSystem
from rag.query_router                import QueryRouter
from rag.hybrid_retriever            import HybridRetriever
from rag.crag_evaluator              import CRAGEvaluator
from rag.reranker                    import HeuristicReranker
from rag.self_rag                    import SelfRAGEvaluator
from models.schemas                  import QueryIntent


class AgentController:

    def __init__(self):
        logger.info("[AGENT] Initializing...")

        self.rag  = Phi3RAG()
        self.ml   = MLClient()
        self.db   = MongoManager()

        # RAG pipeline must init embed_fn first
        _atlas = self.db.get_motor_db()
        _embed = self.rag.embed_fn

        # Memory stores
        self.conversation = ConversationManager(_atlas)
        self.episodic     = EpisodicMemoryStore(_atlas, _embed)
        self.semantic     = SemanticMemoryStore(_atlas, _embed)
        self.working      = WorkingMemoryStore("working_memory.db")
        self.procedural   = ProceduralMemoryStore(_atlas)
        self.trajectory   = TrajectoryMemoryStore(_atlas)
        self.cognitive    = CognitiveMemoryManager("cognitive.db", _atlas, _embed)
        self.knowledge    = KnowledgeGraphStore(_atlas)

        self.gating       = GatingSystem()

        self.query_router = QueryRouter(embedding_fn=_embed)
        self.retriever    = HybridRetriever(atlas_db=_atlas, embedding_fn=_embed)
        self.crag         = CRAGEvaluator(embedding_fn=_embed)
        self.reranker     = HeuristicReranker()
        self.self_rag     = SelfRAGEvaluator()

        logger.info("[AGENT] \u2705 Ready \u2014 all memory + RAG pipeline loaded")


    # ────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ────────────────────────────────────────────────────────────
    async def execute_turn(self, user_id: str, query: str,
                           session_id: str = "default",
                           context: Dict = {}) -> Dict[str, Any]:

        logger.info(f"[AGENT] ===== NEW TURN for user {user_id} =====")

        if not query or not query.strip():
            return self._safe_response(
                "I'm Bandhu, your financial assistant. "
                "I can help with budgets, expenses, savings, and investments. "
                "Could you rephrase your question?",
                session_id, gates_passed=False
            )

        q = query.strip()
        logger.info(f"[AGENT] Step 1: Normalized query: {q}")

        # ── Bill continuation handler (BEFORE everything else) ────────────
        bill_continuation = await self._check_bill_continuation(q, user_id, session_id)
        if bill_continuation:
            return bill_continuation
        # ─────────────────────────────────────────────────────────────────

        # Step 2: Conversation save (non-blocking)
        turns = 0
        try:
            await self.conversation.add_message(session_id, 'user', q)
            turns = await self.conversation.get_turn_count(session_id)
            logger.info(f"[AGENT] Step 2: Continuing session {session_id}")
        except Exception as e:
            logger.warning(f"[AGENT] Conversation save skipped: {e}")

            # Use the new lightweight check_query method
            gate = self.gating.check_query(q)
            if not gate.get("passed", True):
                return self._safe_response(
                    gate.get("message", "I can only help with financial topics."),
                    session_id, gates_passed=False
                )
        except Exception as e:
            logger.warning(f"[AGENT] Gating skipped: {e}")
            # Non-blocking — continue even if gating fails

        # Step 4: Fetch UNIFIED memory context (parallel, non-blocking)
        # ── Mandatory User Profile injection ───────────────────────────
        try:
            db = self.db.get_motor_db()
            user_prof = await db["users"].find_one({"_id": user_id})
            if not user_prof:
                # Basic creation if missing (auto-registration)
                user_prof = {"_id": user_id, "name": "User", "income": 50000.0, "currency": "INR"}
                await db["users"].insert_one(user_prof)
        except Exception as e:
            logger.warning(f"[AGENT] Profile fetch failed: {e}")
            user_prof = {"income": 50000.0}

        intent_map = {
            "transaction":    QueryIntent.SIMPLE_LOOKUP,
            "question":       QueryIntent.FULL_ADVISORY,
            "goal_setting":   QueryIntent.GOAL_PLANNING,
            "goal_query":     QueryIntent.GOAL_PLANNING,
            "profile_update": QueryIntent.SIMPLE_LOOKUP,
        }
        intent_enum = intent_map.get(self._classify_intent(q), QueryIntent.FULL_ADVISORY)

        try:
            unified_ctx = await self.cognitive.get_unified_context(
                user_id=user_id, query=q,
                query_intent=intent_enum,
                session_id=session_id
            )
            
            # Map back to internal variables for the rest of the turn logic
            episodic     = unified_ctx.episodic
            semantic     = unified_ctx.semantic
            working      = unified_ctx.working
            procedural   = [unified_ctx.procedural] if unified_ctx.procedural else []
            trajectory   = unified_ctx.trajectory.__dict__ if unified_ctx.trajectory else {}
            cognitive    = unified_ctx.__dict__
            graph        = unified_ctx.graph_paths
            conv_history = await self.conversation.get_history(session_id, limit=6)
        except Exception as e:
            logger.warning(f"[AGENT] Unified context fetch failed: {e}")
            episodic, semantic, working, procedural, trajectory, cognitive, graph, conv_history = [], [], {}, [], {}, {}, [], []

        context_bundle = {
            "episodic":     episodic,
            "semantic":     semantic,
            "working":      working,
            "procedural":   procedural,
            "trajectory":   trajectory,
            "cognitive":    cognitive,
            "graph":        graph,
            "conversation": conv_history,
            "session_id":   session_id,
            "user_profile": user_prof  # <--- INJECTED
        }
        memory_used = {
            "episodic_count":   len(episodic),
            "semantic_count":   len(semantic),
            "procedural_count": len(procedural),
            "graph_facts":      len(graph),
            "total_memories":   len(episodic) + len(semantic) + len(procedural) + len(graph)
        }

        # Step 5: Intent
        intent = self._classify_intent(q)
        logger.info(f"[AGENT] Step 5: Intent = {intent}")

        # Step 5b: Full RAG pipeline → inject chunks
        rag_chunks = await self._fetch_rag_chunks(q, user_id, intent)
        context_bundle["_rag_chunks"] = rag_chunks

        # Step 6: Intent routing
        if intent == "transaction":
            response_data = await self._handle_transaction(q, user_id, context_bundle)
        elif intent in ("goal_setting", "goal_query"):
            response_data = await self._handle_goal(q, user_id, context_bundle, intent)
        elif intent == "bill_add":
            response_data = await self._handle_bill_add(q, user_id, session_id)
        elif intent == "bill_query":
            response_data = await self._handle_bill_query(user_id)
        elif intent == "tax_query":
            response_data = await self._handle_tax_query(user_id)
        elif intent == "budget_query":
            response_data = await self._handle_budget_query(q, user_id)
        elif intent == "profile_update":
            response_data = await self._handle_profile_update(q, user_id)
        else:
            response_data = self._handle_rag_query(q, context_bundle)

        # Step 6b: SelfRAG quality gate (question intents only)
        if intent == "question" and response_data.get("response"):
            response_data["response"] = await self._verify_response(
                q, intent, "\n".join(rag_chunks), response_data["response"]
            )

        # Step 7: Write to ALL memory (parallel, non-blocking)
        response_text = response_data.get("response", "")
        
        async def safe_run(coro):
            try: await coro
            except Exception as e: logger.warning(f"[AGENT] Memory write skipped: {e}")

        await asyncio.gather(
            safe_run(self.episodic.store_episode(user_id, intent, q, response_text, session_id)),
            safe_run(self._update_semantic_memory(user_id, q, intent, response_text)),
            safe_run(self.working.update_state(user_id, session_id, {"turn_context": {
                 "last_query": q, "last_intent": intent,
                 "timestamp": datetime.now().isoformat()}})),
            safe_run(self._update_procedural_memory(user_id, q, intent, response_data)),
            safe_run(self._update_knowledge_graph(user_id, q, intent)),
            safe_run(self.cognitive.write_episodic(user_id, intent, q, response_text, session_id)),
            safe_run(self.conversation.add_message(session_id, 'assistant', response_text))
        )

        return {
            "response":           response_text,
            "confidence":         response_data.get("confidence", 0.85),
            "memory_used":        memory_used,
            "gates_passed":       True,
            "conversation_turns": turns,
            "intent":             intent
        }


    # ────────────────────────────────────────────────────────────
    # INTENT CLASSIFIER
    # ────────────────────────────────────────────────────────────
    def _classify_intent(self, query: str) -> str:
        q = query.lower()
        TXN = [
            r"i (spent|paid|bought|purchased|ordered|transferred)",
            r"spent [\d\.,]+ (on|at|for)",
            r"paid [\d\.,]+",
            r"\u20b9[\d\.,]+ (on|at|for)",
            r"[\d\.,]+ (rupees?|rs\.?|inr) (on|at|for)",
            r"(lakh|crore|k) (on|at|for)",
        ]
        for p in TXN:
            if re.search(p, q): return "transaction"

        # Bill Add intent — must come before transaction to avoid misrouting
        BILL_ADD = [
            r"(bill|emi|rent|electricity|gas|subscription|due|payment).*\d",
            r"\d.*(bill|emi|rent|electricity|due).*(due|on|by)",
            r"(have|got|need to pay).*(bill|rent|emi)",
            r"remind.*pay",
            r"add.*bill",
        ]
        for p in BILL_ADD:
            if re.search(p, q): return "bill_add"

        # Bill Query intent
        BILL_Q = [
            r"(upcoming|due|pending|my) bills?",
            r"what.*bills?",
            r"show.*bills?",
            r"how much.*due",
            r"any bills?",
        ]
        for p in BILL_Q:
            if re.search(p, q): return "bill_query"

        # Tax / 80C query
        TAX_Q = [
            r"80c", r"tax.*(saving|saved|invest)",
            r"(elss|ppf|nps|lic|epf).*invest",
            r"tax.*(tracker|limit|deduct|benefit)",
            r"how much.*invest.*tax",
            r"section 80",
        ]
        for p in TAX_Q:
            if re.search(p, q): return "tax_query"

        # Budget query
        BUDGET_Q = [
            r"(budget|spending).*(status|health|progress|left)",
            r"how.*budget",
            r"over budget",
            r"am i on track",
            r"category.*spend",
        ]
        for p in BUDGET_Q:
            if re.search(p, q): return "budget_query"

        GOAL_SET = [
            r"saving for", r"my goal is", r"i want to save",
            r"planning to (buy|save)", r"europe trip", r"target.*lakh"
        ]
        for p in GOAL_SET:
            if re.search(p, q): return "goal_setting"

        GOAL_Q = [
            r"progress.*goal", r"how.*saving", r"on track",
            r"when will i", r"achieve.*goal", r"travel goal"
        ]
        for p in GOAL_Q:
            if re.search(p, q): return "goal_query"

        # Profile Update intent (Salary, Income)
        PROFILE_UPD = [
            r"my (salary|income|earnings?) (is|set to|increased to)",
            r"i (earn|make) [\u20b9\d,]+",
            r"update my (salary|income)",
            r"change income to",
        ]
        for p in PROFILE_UPD:
            if re.search(p, q): return "profile_update"

        return "question"


    # ────────────────────────────────────────────────────────────
    # RAG PIPELINE
    # ────────────────────────────────────────────────────────────
    async def _fetch_rag_chunks(self, query: str,
                                 user_id: str, intent: str) -> list:
        try:
            route = await self.query_router.route(query, user_id)
            logger.info(f"[AGENT] Route: {route.intent.value} "
                        f"tiers={route.tiers_to_query} "
                        f"conf={route.confidence:.2f}")
            if route.db_direct:
                return []

            raw = await self.retriever.retrieve(
                query=query, user_id=user_id,
                tiers=route.tiers_to_query, top_k=12
            )
            if not raw:
                return []

            import numpy as np
            q_emb = None
            if self.rag.embed_fn:
                try:
                    loop = asyncio.get_event_loop()
                    vec  = await loop.run_in_executor(None, self.rag.embed_fn, query)
                    if vec:
                        q_emb = np.array(vec, dtype=np.float32)
                except Exception:
                    pass

            graded   = await self.crag.evaluate_chunks(query, raw, q_emb)
            kept     = [c for c in graded if c.decision != "DISCARD"]
            if not kept:
                web = await self.crag.fetch_web_fallback(route.intent.value)
                return [web] if web else []

            reranked   = self.reranker.rerank(query, kept)
            injectable = self.crag.get_injectable_content(reranked)
            chunks     = [c for c in injectable.split("\n") if c.strip()]

            logger.info(
                f"[AGENT] RAG: {len(chunks)} chunks "
                f"(KEEP={sum(1 for c in graded if c.decision=='KEEP')} "
                f"TRIM={sum(1 for c in graded if c.decision=='TRIM')} "
                f"DISCARD={sum(1 for c in graded if c.decision=='DISCARD')})"
            )
            return chunks
        except Exception as e:
            logger.warning(f"[AGENT] RAG pipeline skipped: {e}")
            return []


    async def _verify_response(self, query: str, intent: str,
                                context: str, response: str) -> str:
        try:
            from models.schemas import QueryIntent as QI
            intent_map = {
                "transaction":  QI.SIMPLE_LOOKUP,
                "question":     QI.FULL_ADVISORY,
                "goal_setting": QI.GOAL_PLANNING,
                "goal_query":   QI.GOAL_PLANNING,
            }
            verdict = await self.self_rag.evaluate_response(
                query              = query,
                query_intent       = intent_map.get(intent, QI.FULL_ADVISORY),
                context_injected   = context,
                generated_response = response,
                graded_chunks      = []
            )

            if verdict.passed:
                logger.info("[AGENT] SelfRAG ✅ passed")
                return response

            # ── Hard block for hallucinated legal/tax sections ────────────────
            if "NO_HALLUCINATION" in verdict.failed_criteria:
                logger.warning("[AGENT] SelfRAG 🚨 HALLUCINATION detected — replacing response")
                return self._safe_financial_response(query, context)

            # Other failures (GROUNDED, USEFUL) — soft pass with disclaimer
            logger.warning(f"[AGENT] SelfRAG ⚠️  soft fail: {verdict.failed_criteria}")
            return response + (
                "\n\n⚠️ *Note: Please verify specific figures at "
                "[incometax.gov.in](https://incometax.gov.in)*"
            )

        except Exception as e:
            logger.warning(f"[AGENT] SelfRAG skipped: {e}")
            return response

    def _safe_financial_response(self, query: str, context: str) -> str:
        """
        Fallback when hallucination is detected.
        Never fabricates section numbers — always redirects to official sources.
        """
        q = query.lower()

        # Tax / section query fallback
        if any(w in q for w in ["tax", "section", "income tax", "itr", "tds", "gst"]):
            return (
                "For accurate tax information specific to your situation, "
                "please refer to the official sources:\n\n"
                "📋 **Income Tax Act sections:** [incometax.gov.in](https://incometax.gov.in)\n"
                "📋 **GST rules:** [gst.gov.in](https://gst.gov.in)\n\n"
                "I can help with general concepts like tax slabs, 80C deductions, "
                "or HRA exemptions — but for specific legal sections and penalties, "
                "always verify with a CA or the official portal."
            )

        # Black money / illegal query fallback
        if any(w in q for w in ["black money", "convert", "white money", "unaccounted", "illegal"]):
            return (
                "Converting unaccounted income into declared income must be done "
                "legally through proper ITR filing.\n\n"
                "⚠️ Any method involving misrepresentation is illegal under "
                "the Income Tax Act.\n\n"
                "✅ **Legal path:** Declare all income in your ITR. "
                "Consult a Chartered Accountant for specific guidance.\n\n"
                "*For exact penalty sections, verify at [incometax.gov.in](https://incometax.gov.in)*"
            )

        # Generic safe fallback
        return (
            "I want to give you accurate information, but I'm not confident "
            "enough in the specific details to answer this safely. "
            "Please verify at [incometax.gov.in](https://incometax.gov.in) "
            "or consult a qualified financial advisor."
        )



    # ────────────────────────────────────────────────────────────
    # TRANSACTION HANDLER
    # ────────────────────────────────────────────────────────────
    async def _handle_transaction(self, query: str,
                                   user_id: str, context: Dict) -> Dict:
        extracted = self._extract_transaction(query)
        amount    = extracted.get("amount", 0)
        merchant  = extracted.get("description", "Unknown")

        if amount <= 0:
            return {"response":
                "I couldn't detect a valid amount. "
                "Try: 'I spent \u20b9500 on Swiggy'", "confidence": 0.6}

        # Categorize
        category, conf = "Other", 0.0
        try:
            r = await self.ml.post("/ml/categorize",
                                   {"descriptions": [merchant]})
            items = r if isinstance(r, list) else r.get("results", [])
            if items:
                category = items[0].get("category", "Other")
                conf     = float(items[0].get("confidence", 0.0))
        except Exception as e:
            logger.warning(f"[AGENT] Categorize skipped: {e}")

        # Anomaly detect
        is_anomaly, score, severity, reason = False, 0.0, "LOW", ""
        try:
            r = await self.ml.post("/ml/anomalies", {
                "transactions": [{
                    "transaction_id": "temp",
                    "date": datetime.now().isoformat()[:10],
                    "description": merchant, "amount": amount,
                    "transaction_type": "Debit",
                    "balance": 0, "category": category
                }], "history": []
            })
            anoms = r if isinstance(r, list) else r.get("anomalies", [])
            if anoms:
                a          = anoms[0]
                is_anomaly = a.get("is_anomaly", False)
                score      = float(a.get("anomaly_score", 0.0))
                severity   = a.get("severity", "LOW")
                reason     = a.get("reason", "")
        except Exception as e:
            logger.warning(f"[AGENT] Anomaly skipped: {e}")

        # Save to MongoDB
        try:
            await self.db.transactions.insert_one({
                "user_id": user_id, "description": merchant,
                "amount": amount, "category": category,
                "category_confidence": conf,
                "categorization_method": "ml" if conf > 0 else "rule",
                "type": "Debit", "source": "chat",
                "date": datetime.now().isoformat()[:10],
                "is_anomaly": is_anomaly, "anomaly_score": score,
                "anomaly_severity": severity,
                "created_at": datetime.now().isoformat()
            })
        except Exception as e:
            logger.warning(f"[AGENT] Save skipped: {e}")

        # Format amount
        if amount >= 10_000_000:
            amt = f"\u20b9{amount/10_000_000:.2f} Crore (\u20b9{amount:,.0f})"
        elif amount >= 100_000:
            amt = f"\u20b9{amount/100_000:.2f} Lakh (\u20b9{amount:,.0f})"
        else:
            amt = f"\u20b9{amount:,.0f}"

        anomaly_block = ""
        if is_anomaly and severity in ("HIGH", "MEDIUM"):
            anomaly_block = f"\n\n\u26a0\ufe0f **Anomaly!** Severity: {severity}\n{reason}"

        return {
            "response": (
                f"\u2705 **Transaction Recorded**\n\n"
                f"\U0001f4dd **Details:**\n"
                f"\u2022 Amount: {amt}\n"
                f"\u2022 Item: {merchant}\n"
                f"\u2022 Category: {category}\n\n"
                f"\U0001f916 **ML Results:**\n"
                f"\u2022 Confidence: {conf*100:.1f}%\n"
                f"\u2022 Anomaly Score: {score:.2f}\n"
                f"\u2022 Severity: {severity}"
                f"{anomaly_block}"
            ),
            "confidence": 0.95,
            "amount": amount, "description": merchant, "category": category
        }


    def _extract_transaction(self, query: str) -> Dict:
        q = query.lower()
        amount = 0.0
        for pattern, multiplier in [
            (r'([\d\.]+)\s*crore',   10_000_000),
            (r'([\d\.]+)\s*lakh',    100_000),
            (r'([\d\.]+)\s*k\b',     1_000),
            (r'([\d,]+(?:\.\d+)?)',  1),
        ]:
            m = re.search(pattern, q)
            if m:
                amount = float(m.group(1).replace(',', '')) * multiplier
                break

        merchant = "Unknown Purchase"
        MERCHANTS = [
            "swiggy","zomato","uber","ola","amazon","flipkart","netflix",
            "jio","airtel","bigbasket","zepto","blinkit","apollo","1mg",
            "zerodha","groww","makemytrip","irctc","petrol","fuel",
            "electricity","metro","rapido","dominos","kfc","myntra",
            "nykaa","unacademy","byjus","paytm","phonepe","gpay","oyo"
        ]
        for kw in MERCHANTS:
            if kw in q:
                merchant = kw.capitalize()
                break
        m = re.search(
            r'(?:on|at|for|from)\s+([A-Za-z][A-Za-z\s]{1,25}?)'
            r'(?:\s+today|\s+yesterday|$|\.)',
            query, re.IGNORECASE
        )
        if m:
            c = m.group(1).strip()
            if len(c) > 2 and c.lower() not in ('a','an','the','my'):
                merchant = c

        return {"amount": amount, "description": merchant}


    # ────────────────────────────────────────────────────────────
    # BILL HANDLERS (Atlas DB)
    # ────────────────────────────────────────────────────────────
    def _extract_bill(self, query: str) -> Dict:
        """Extract bill fields from natural language. None = missing."""
        q = query.lower()

        # Amount
        amount = None
        for pat, mult in [
            (r'([\d\.]+)\s*(?:lakh|lac)', 100_000),
            (r'([\d\.]+)\s*k\b', 1_000),
            (r'₹\s*([\d,]+(?:\.\d+)?)', 1),
            (r'rs\.?\s*([\d,]+(?:\.\d+)?)', 1),
            (r'([\d,]+(?:\.\d+)?)\s*(?:rupees?|rs)', 1),
            (r'([\d,]+(?:\.\d+)?)', 1),
        ]:
            m = re.search(pat, q)
            if m:
                try:
                    amount = float(m.group(1).replace(',', '')) * mult
                except Exception:
                    pass
                break

        # Title
        title = None
        BILL_WORDS = [
            "electricity", "light bill", "power bill", "rent", "gas", "water",
            "internet", "wifi", "broadband", "mobile", "phone", "recharge",
            "netflix", "amazon prime", "hotstar", "disney", "spotify",
            "insurance", "lic", "credit card", "emi", "loan", "school fee",
            "college fee", "tuition", "society maintenance", "maintenance",
            "gym", "yoga", "subscription",
        ]
        for kw in BILL_WORDS:
            if kw in q:
                title = kw.replace(" bill", "").title()
                break
        if not title:
            m = re.search(r'(?:for|my|the|pay)\s+([a-z][a-z\s]{1,20}?)\s+(?:bill|due|payment|emi)', q)
            if m:
                title = m.group(1).strip().title()

        # Due date — natural language parsing
        due_date = self._parse_date(q)

        # Category from title
        category = "Bills & Utilities"
        if title:
            tl = title.lower()
            if any(w in tl for w in ["rent", "society", "maintenance"]): category = "Housing"
            elif any(w in tl for w in ["emi", "loan", "credit"]): category = "Finance"
            elif any(w in tl for w in ["netflix", "spotify", "prime", "hotstar"]): category = "Entertainment"
            elif any(w in tl for w in ["school", "college", "tuition"]): category = "Education"
            elif any(w in tl for w in ["phone", "mobile", "recharge"]): category = "Telecom"

        return {"title": title, "amount": amount, "due_date": due_date, "category": category}

    def _parse_date(self, text: str) -> Optional[str]:
        """Parse a natural language date into YYYY-MM-DD or None."""
        now = datetime.utcnow()
        t = text.lower()

        if "tomorrow" in t:
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if "today" in t:
            return now.strftime("%Y-%m-%d")
        if "next week" in t:
            return (now + timedelta(weeks=1)).strftime("%Y-%m-%d")

        # "1st", "2nd", "3rd", "21st", etc.
        m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', t)
        if m:
            MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                      "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            day = int(m.group(1))
            mon = MONTHS[m.group(2)]
            year = now.year
            # If month already passed this year, use next year
            if mon < now.month or (mon == now.month and day < now.day):
                year += 1
            return f"{year}-{mon:02d}-{day:02d}"

        # "April 1" / "1 April"
        m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})', t)
        if m:
            MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                      "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            mon = MONTHS[m.group(1)[:3]]
            day = int(m.group(2))
            year = now.year
            if mon < now.month or (mon == now.month and day < now.day):
                year += 1
            return f"{year}-{mon:02d}-{day:02d}"

        # "YYYY-MM-DD" or "DD/MM/YYYY"
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', t)
        if m: return m.group(0)
        m = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', t)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3) or str(now.year)
            return f"{y}-{int(mo):02d}-{int(d):02d}"

        # plain day number "on the 5th", "by 28"
        m = re.search(r'(?:by|on|before|due)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s|$)', t)
        if m:
            day = int(m.group(1))
            mo = now.month
            yr = now.year
            if day < now.day: mo += 1
            if mo > 12: mo, yr = 1, yr + 1
            return f"{yr}-{mo:02d}-{day:02d}"

        return None

    async def _check_bill_continuation(self, query: str, user_id: str, session_id: str) -> Optional[Dict]:
        """Check Atlas for a pending bill awaiting completion, merge new info if found."""
        try:
            db = self.db.get_motor_db()
            pending = await db["agent_working_memory"].find_one(
                {"user_id": user_id, "session_id": session_id, "type": "pending_bill"}
            )
            if not pending:
                return None

            # Merge new info from query
            bill = dict(pending.get("bill", {}))
            extracted = self._extract_bill(query)

            # Fill in any still-missing fields
            if not bill.get("amount")  and extracted.get("amount"):   bill["amount"]   = extracted["amount"]
            if not bill.get("due_date") and extracted.get("due_date"): bill["due_date"] = extracted["due_date"]
            if not bill.get("title")   and extracted.get("title"):    bill["title"]    = extracted["title"]

            # Still missing something?
            if not bill.get("amount"):
                await db["agent_working_memory"].update_one(
                    {"user_id": user_id, "session_id": session_id, "type": "pending_bill"},
                    {"$set": {"bill": bill}}
                )
                return self._safe_response(
                    f"Sure! How much is the {bill.get('title','bill')}? Please give me the amount. 💰",
                    session_id
                )
            if not bill.get("due_date"):
                await db["agent_working_memory"].update_one(
                    {"user_id": user_id, "session_id": session_id, "type": "pending_bill"},
                    {"$set": {"bill": bill}}
                )
                return self._safe_response(
                    f"Got it — ₹{bill['amount']:,.0f} for {bill.get('title','the bill')}. When is it due? 📅",
                    session_id
                )

            # All fields complete — write to bills collection
            await db["bills"].insert_one({
                "user_id":    user_id,
                "title":      bill.get("title", "Bill"),
                "amount":     bill["amount"],
                "due_date":   bill["due_date"],
                "category":   bill.get("category", "Bills & Utilities"),
                "source":     "chat",
                "created_at": datetime.utcnow().isoformat()
            })
            # Clear the pending context
            await db["agent_working_memory"].delete_one(
                {"user_id": user_id, "session_id": session_id, "type": "pending_bill"}
            )

            # Format urgency
            try:
                due_dt = datetime.strptime(bill["due_date"][:10], "%Y-%m-%d")
                days = (due_dt.date() - datetime.utcnow().date()).days
                urgency = ("🔴 Due today!" if days == 0 else
                           f"🟠 Due in {days} day{'s' if days != 1 else ''}" if days <= 3 else
                           f"🟡 Due in {days} days")
            except Exception:
                urgency = ""

            return self._safe_response(
                f"✅ **Bill Added!** {bill.get('title','Bill')}: ₹{bill['amount']:,.0f} due {bill['due_date']} {urgency}\n"
                f"It'll appear in your dashboard right away! 🎉",
                session_id
            )

        except Exception as e:
            logger.warning(f"[AGENT] Bill continuation check failed: {e}")
            return None

    async def _handle_bill_add(self, query: str, user_id: str, session_id: str) -> Dict:
        """Handle bill_add intent: extract, store if partial, complete if full."""
        extracted = self._extract_bill(query)
        title    = extracted.get("title")
        amount   = extracted.get("amount")
        due_date = extracted.get("due_date")
        category = extracted.get("category", "Bills & Utilities")

        try:
            db = self.db.get_motor_db()

            if not title:
                return {"response": "What is this bill for? (e.g. electricity, rent, Netflix) 🧾", "confidence": 0.9}

            if not amount:
                # Save partial to Atlas
                await db["agent_working_memory"].update_one(
                    {"user_id": user_id, "session_id": session_id, "type": "pending_bill"},
                    {"$set": {"bill": {"title": title, "amount": None, "due_date": due_date, "category": category},
                              "updated_at": datetime.utcnow().isoformat()}},
                    upsert=True
                )
                return {"response": f"Got it — **{title}** bill! How much is it? 💰", "confidence": 0.9}

            if not due_date:
                # Save partial to Atlas
                await db["agent_working_memory"].update_one(
                    {"user_id": user_id, "session_id": session_id, "type": "pending_bill"},
                    {"$set": {"bill": {"title": title, "amount": amount, "due_date": None, "category": category},
                              "updated_at": datetime.utcnow().isoformat()}},
                    upsert=True
                )
                return {"response": f"₹{amount:,.0f} for **{title}** — noted! When is it due? 📅\n\n(e.g. 'April 5', '1st of next month', 'tomorrow')", "confidence": 0.9}

            # All fields present — write directly
            await db["bills"].insert_one({
                "user_id":    user_id,
                "title":      title,
                "amount":     amount,
                "due_date":   due_date,
                "category":   category,
                "source":     "chat",
                "created_at": datetime.utcnow().isoformat()
            })

            try:
                due_dt = datetime.strptime(due_date[:10], "%Y-%m-%d")
                days = (due_dt.date() - datetime.utcnow().date()).days
                urgency = ("🔴 Due today!" if days == 0 else
                           f"🟠 Due in {days} day{'s' if days != 1 else ''}" if days <= 3 else
                           f"🟡 Due in {days} days")
            except Exception:
                urgency = ""

            return {
                "response": (
                    f"✅ **Bill Added to Dashboard!**\n\n"
                    f"📋 **{title}**: ₹{amount:,.0f}\n"
                    f"📅 Due: {due_date} {urgency}\n\n"
                    f"It'll appear in your **Upcoming Bills** card right away! 🎉"
                ),
                "confidence": 0.95
            }
        except Exception as e:
            logger.warning(f"[AGENT] Bill add failed: {e}")
            return {"response": f"I noted your {title or 'bill'} — please add it again if it doesn't appear.", "confidence": 0.7}

    async def _handle_bill_query(self, user_id: str) -> Dict:
        """Fetch upcoming bills from Atlas and format for chat."""
        try:
            db = self.db.get_motor_db()
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            cursor = db["bills"].find(
                {"user_id": user_id, "due_date": {"$gte": today_str}}
            ).sort("due_date", 1).limit(5)
            bills = await cursor.to_list(length=5)

            if not bills:
                return {"response": "No upcoming bills! You can add one by saying something like:\n'I have electricity bill of ₹2,300 due April 5th'", "confidence": 0.9}

            lines = ["📋 **Your Upcoming Bills:**\n"]
            total = 0
            for b in bills:
                try:
                    due_dt = datetime.strptime(b["due_date"][:10], "%Y-%m-%d")
                    days = (due_dt.date() - datetime.utcnow().date()).days
                    urgency = "🔴" if days <= 2 else "🟠" if days <= 7 else "🟡"
                except Exception:
                    days, urgency = 0, "📅"
                lines.append(f"{urgency} **{b['title']}**: ₹{b['amount']:,.0f} — due {b['due_date']} ({days} days)")
                total += b.get("amount", 0)
            lines.append(f"\n💰 **Total Due**: ₹{total:,.0f}")
            return {"response": "\n".join(lines), "confidence": 0.95}
        except Exception as e:
            logger.warning(f"[AGENT] Bill query failed: {e}")
            return {"response": "I couldn't load your bills right now. Try the dashboard for full details.", "confidence": 0.6}

    async def _handle_tax_query(self, user_id: str) -> Dict:
        """Scan FY transactions for 80C investments and report."""
        try:
            db = self.db.get_motor_db()
            now = datetime.utcnow()
            fy_start = f"{now.year - 1 if now.month < 4 else now.year}-04-01"
            fy_end   = f"{now.year if now.month >= 4 else now.year - 1}-03-31"

            KEYWORDS_80C = ["elss","ppf","nps","lic","epf","tax saver","equity linked",
                            "jeevan","hdfc life","sbi life","sukanya","ulip"]

            cursor = db["transactions"].find({
                "user_id": user_id,
                "type": "debit",
                "date": {"$gte": fy_start, "$lte": fy_end}
            })
            txns = await cursor.to_list(length=5000)

            invested = 0.0
            breakdown = {}
            for t in txns:
                desc = (t.get("description","") + " " + t.get("category","")).lower()
                for kw in KEYWORDS_80C:
                    if kw in desc:
                        invested += t.get("amount", 0)
                        breakdown[kw] = breakdown.get(kw, 0) + t.get("amount", 0)
                        break

            limit = 150000
            remaining = max(0, limit - invested)
            user = await db["users"].find_one({"_id": user_id})
            annual_income = (user.get("income", 50000) if user else 50000) * 12
            slab = 0.30 if annual_income > 1500000 else 0.20 if annual_income > 1000000 else 0.10
            tax_saved = round(min(invested, limit) * slab, 0)

            if invested == 0:
                return {"response": (
                    "📊 **80C Tracker**\n\n"
                    "I couldn't find any 80C investments in your transactions this FY.\n\n"
                    "💡 Start with ELSS mutual funds — shortest 3-year lock-in, tax-free returns!\n"
                    f"You can save up to ₹{limit:,} under Section 80C (potential tax saving: ₹{round(limit*slab):,}/year)"
                ), "confidence": 0.9}

            lines = [f"📊 **80C Tracker — FY {fy_start[:4]}-{fy_end[:4]}**\n"]
            lines.append(f"✅ Invested: **₹{invested:,.0f}** / ₹{limit:,} limit")
            lines.append(f"💰 Tax Saved: **₹{tax_saved:,.0f}**")
            lines.append(f"📉 Remaining Limit: **₹{remaining:,.0f}**")
            if breakdown:
                lines.append("\n🔍 **Breakdown:**")
                for k, v in breakdown.items():
                    lines.append(f"  • {k.upper()}: ₹{v:,.0f}")
            if remaining > 0:
                lines.append(f"\n💡 Invest ₹{remaining:,.0f} more in ELSS to save another ₹{round(remaining*slab):,.0f} in taxes!")
            return {"response": "\n".join(lines), "confidence": 0.95}
        except Exception as e:
            logger.warning(f"[AGENT] Tax query failed: {e}")
            return {"response": "I couldn't load your tax data right now. Check the dashboard for the 80C Tracker.", "confidence": 0.6}

    async def _handle_budget_query(self, query: str, user_id: str) -> Dict:
        """Fetch budget + live spending from Atlas and report."""
        try:
            db = self.db.get_motor_db()
            now = datetime.utcnow()
            month_start = now.strftime("%Y-%m-01")

            # Live spend per category
            pipeline = [
                {"$match": {"user_id": user_id, "type": "debit", "date": {"$gte": month_start}}},
                {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
            ]
            agg = await db["transactions"].aggregate(pipeline).to_list(100)
            spend_map = {r["_id"]: r["total"] for r in agg}
            total_spent = sum(spend_map.values())

            budget = await db["budgets"].find_one({"user_id": user_id})
            user = await db["users"].find_one({"_id": user_id})
            income = user.get("income", 50000) if user else 50000
            total_budget = budget.get("total_income", income) if budget else income

            pct = round(total_spent / max(1, total_budget) * 100, 1)
            status = "🔴 Critical" if pct > 90 else "🟠 High" if pct > 70 else "🟢 Healthy"

            lines = [f"💼 **Budget Status — {now.strftime('%B %Y')}**\n",
                     f"{status} — {pct}% used",
                     f"💸 Spent: ₹{total_spent:,.0f} / ₹{total_budget:,.0f}\n",
                     "**Top Categories:**"]

            for cat, amt in sorted(spend_map.items(), key=lambda x: -x[1])[:5]:
                pct_cat = round(amt / max(1, total_budget) * 100, 1)
                bar = "█" * min(int(pct_cat / 5), 20)
                lines.append(f"  {cat}: ₹{amt:,.0f} ({pct_cat}%) {bar}")

            return {"response": "\n".join(lines), "confidence": 0.95}
        except Exception as e:
            logger.warning(f"[AGENT] Budget query failed: {e}")
            return {"response": "I couldn't load budget data right now. Check the dashboard for details.", "confidence": 0.6}

    async def _handle_profile_update(self, query: str, user_id: str) -> Dict:
        """Extract income and update the users collection + dashboard."""
        try:
            # Re-use transaction amount extractor for income
            data = self._extract_transaction(query)
            income = data.get("amount", 0)
            
            if income <= 0:
                # Retry with specific regex if merchant-based extractor failed
                m = re.search(r'(\d[\d,]*\.?\d*)', query)
                if m:
                    income = float(m.group(1).replace(',', ''))

            if income <= 0:
                return {"response": "I couldn't catch the exact amount. Could you say 'My salary is ₹50,000'?", "confidence": 0.8}

            # 1. Update primary User profile (for dashboard)
            db = self.db.get_motor_db()
            await db["users"].update_one(
                {"_id": user_id},
                {"$set": {"income": income}},
                upsert=True
            )
            
            # 2. Update budgets collection if exists
            await db["budgets"].update_one(
                {"user_id": user_id},
                {"$set": {"total_income": income}},
                upsert=False
            )

            # 3. Confirmation
            return {
                "response": (
                    f"✅ **Profile Updated!**\n\n"
                    f"💰 **Monthly Income:** ₹{income:,.0f}\n"
                    f"I've updated your dashboard and budget limit right away! 🎉"
                ),
                "confidence": 0.95
            }
        except Exception as e:
            logger.warning(f"[AGENT] Profile update failed: {e}")
            return {"response": "I encountered an error updating your profile. Please try again.", "confidence": 0.5}


    # ────────────────────────────────────────────────────────────
    # GOAL HANDLER
    # ────────────────────────────────────────────────────────────
    async def _handle_goal(self, query: str, user_id: str,
                            context: Dict, intent: str) -> Dict:
        if intent == "goal_setting":
            try:
                await self.episodic.store_episode(
                    user_id, "goal_setting",
                    query, f"User set goal: {query[:100]}",
                    session_id=context.get("session_id")
                )
            except Exception:
                pass

        result = self.rag.generate(query=query, context=context)
        response = result.get("result", "")
        if not response or len(response) < 20:
            if intent == "goal_setting":
                response = (
                    "Great! I've noted your goal. "
                    "Set it up in the Goals section to track progress automatically."
                )
            else:
                ep_goals = [
                    m.get("event_summary", "") for m in context.get("episodic", [])
                    if any(w in m.get("event_summary", "").lower()
                           for w in ["goal","saving","europe","trip","lakh"])
                ]
                response = (
                    f"Based on your goals: {'; '.join(ep_goals[:2])}. "
                    "Check the Goals tab for AI-verified ETAs."
                    if ep_goals else
                    "Check the Goals section for your progress and ETAs."
                )
        return {"response": response, "confidence": 0.85}


    # ────────────────────────────────────────────────────────────
    # RAG QUERY HANDLER
    # ────────────────────────────────────────────────────────────
    def _handle_rag_query(self, query: str, context: Dict) -> Dict:
        result = self.rag.generate(
            query=query, context=context,
            max_length=600, temperature=0.3
        )
        return {"response": result.get("result", ""), "confidence": 0.85}


    # ────────────────────────────────────────────────────────────
    # MEMORY WRITE HELPERS
    # ────────────────────────────────────────────────────────────
    async def _update_semantic_memory(self, user_id, query, intent, response):
        q = query.lower()
        facts = []
        m = re.search(r'(salary|earn|income).*?([\d,]+)', q)
        if m:
            facts.append(("monthly_income", f"\u20b9{m.group(2).replace(',','')}", "income"))
        if any(w in q for w in ["saving for","goal is","want to buy"]):
            facts.append(("active_goal", query[:100], "goal"))
        for city in ["mumbai","delhi","bangalore","pune","hyderabad","chennai"]:
            if city in q:
                facts.append(("city", city.capitalize(), "location"))
        for inst in ["ppf","elss","sip","fd","gold","nps"]:
            if inst in q:
                facts.append(("investment_interest", inst.upper(), "investment"))
        for attr, value, source in facts:
            try:
                await self.semantic.upsert_fact(user_id, "USER_PROFILE", attr, value, 0.75)
            except Exception:
                pass

    async def _update_procedural_memory(self, user_id, query, intent, data):
        if intent != "transaction":
            return
        amount   = data.get("amount", 0)
        category = data.get("category", "Other")
        merchant = data.get("description", "")
        if amount > 0:
            try:
                await self.procedural.record_pattern(
                    user_id=user_id,
                    pattern=f"Spent \u20b9{amount:,.0f} on {merchant} ({category})",
                    category=category, amount=amount,
                    metadata={"merchant": merchant,
                              "timestamp": datetime.now().isoformat()}
                )
            except Exception:
                pass

    async def _update_knowledge_graph(self, user_id, query, intent):
        q = query.lower()
        LINKS = {
            "zerodha": [("is_a","Investment Platform"),("enables","Stock Trading")],
            "ppf":     [("is_a","Tax Saving"),("section","80C")],
            "elss":    [("is_a","Mutual Fund"),("section","80C"),("lock_in","3yr")],
            "swiggy":  [("is_a","Food Delivery"),("category","Food & Dining")],
            "sip":     [("is_a","Investment Method"),("for","Mutual Funds")],
        }
        for entity, links in LINKS.items():
            if entity in q:
                for rel, target in links:
                    try:
                        await self.knowledge.add_fact(
                            user_id=user_id, subject=entity,
                            relation=rel, obj=target, source="conversation"
                        )
                    except Exception:
                        pass


    # ────────────────────────────────────────────────────────────
    # HELPERS
    # ────────────────────────────────────────────────────────────
    def _safe_response(self, msg, session_id, gates_passed=True):
        return {
            "response": msg, "confidence": 0.85,
            "memory_used": {"episodic_count":0,"semantic_count":0,"total_memories":0},
            "gates_passed": gates_passed,
            "conversation_turns": 0, "intent": "blocked"
        }
