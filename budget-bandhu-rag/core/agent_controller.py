"""
core/agent_controller.py — Single source of truth for all chat logic.
"""
import logging, re, asyncio
from typing import Dict, Any
from datetime import datetime

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
        intent_map = {
            "transaction":  QueryIntent.SIMPLE_LOOKUP,
            "question":     QueryIntent.FULL_ADVISORY,
            "goal_setting": QueryIntent.GOAL_PLANNING,
            "goal_query":   QueryIntent.GOAL_PLANNING,
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
            working      = {item.content_type: item.content_json for item in unified_ctx.working}
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
            "session_id":   session_id
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
            safe_run(self.working.add(session_id, user_id, "turn_context", {
                 "last_query": q, "last_intent": intent,
                 "timestamp": datetime.now().isoformat()})),
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
