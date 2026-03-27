"""
Agent Controller - The Sovereign Authority (Enhanced with Conversation Support)
Controls the entire agentic lifecycle with multi-turn conversation tracking.

Features:
- 9-step agentic workflow
- Multi-turn conversation history
- Session management
- Memory retrieval (episodic + semantic)
- Validation gating
- Conservative learning
- Full conversation context

Author: Aryan Lomte
Date: Jan 16, 2026
Version: 2.0.0
"""
from typing import Dict, Optional, List
from datetime import datetime
import uuid

from memory.memory_manager import MemoryManager
from memory.conversation_manager import ConversationManager
from intelligence.phi3_rag import Phi3RAG
from core.gating import GatingSystem
import re
from api.database import Database


class AgentController:
    """
    Enhanced agent controller with conversation history support.
    
    The controller decides:
    - When to speak
    - When to warn vs advise
    - When learning is permitted
    - What enters memory
    - How conversation history affects context
    
    The LLM never makes these decisions.
    """
    
    def __init__(
        self,
        phi3_rag: Phi3RAG,
        memory_manager: MemoryManager,
        conversation_manager: ConversationManager,
        gating_system: Optional[GatingSystem] = None,
        categorizer = None
    ):
        """
        Initialize agent controller with all required managers.
        
        Args:
            phi3_rag: Phi-3.5 RAG intelligence component
            memory_manager: Memory operations manager (episodic + semantic)
            conversation_manager: Conversation history manager
            gating_system: Validation gates (optional, uses default if None)
            categorizer: Transaction categorization engine (optional)
        """
        self.phi3 = phi3_rag
        self.memory = memory_manager
        self.conversation = conversation_manager
        self.gating = gating_system or GatingSystem()
        self.categorizer = categorizer
        
        # Statistics tracking
        self.stats = {
            'total_turns': 0,
            'successful_turns': 0,
            'failed_gates': 0,
            'memories_used': 0
        }
        
        print("[AGENT] Agent Controller initialized with conversation support")
    
    async def execute_turn(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Execute one conversation turn with full agentic workflow.
        
        The immutable 9-step lifecycle:
        
        STEP 1: Input normalization
        STEP 2: Session management (create/resume)
        STEP 3: Memory retrieval (episodic + semantic)
        STEP 4: Conversation history retrieval (multi-turn context)
        STEP 5: Context reconstruction (memory + history)
        STEP 6: Model reasoning (Phi-3.5 proposes)
        STEP 7: Controller gating (validation)
        STEP 8: Response delivery + storage
        STEP 9: Observation & learning evaluation
        
        Args:
            user_id: User identifier
            query: User's question/command
            session_id: Optional conversation session ID (creates new if None)
        
        Returns:
            {
                'response': str,              # Final response to user
                'session_id': str,            # Session identifier
                'confidence': float,          # Model confidence (0-1)
                'memory_used': {              # Memory context used
                    'episodic_count': int,
                    'semantic_count': int
                },
                'conversation_turns': int,    # Number of turns in session
                'gates_passed': bool,         # Validation result
                'metadata': {                 # Additional metadata
                    'latency_seconds': float,
                    'model': str,
                    'timestamp': str
                }
            }
        """
        self.stats['total_turns'] += 1
        print(f"\n[AGENT] ===== NEW TURN for user {user_id} =====")
        
        # ================================================================
        # STEP 1: Input normalization
        # ================================================================
        normalized_query = self._normalize_input(query)
        print(f"[AGENT] Step 1: Normalized query: {normalized_query}")
        
        # Check Intent (Transaction Override)
        intent_result = await self._check_intent_and_execute(user_id, normalized_query)
        if intent_result:
             print(f"[AGENT] Intent Tool Executed: {intent_result}")
             # We assume session management handles this or we just skip standard flow
             # Ideally trigger session logic too?
             if not session_id:
                 session_id = await self.conversation.create_session(user_id)
                 
             await self.conversation.add_message(session_id, 'user', query)
             await self.conversation.add_message(session_id, 'assistant', intent_result)
             
             return {
                 'response': intent_result,
                 'session_id': session_id,
                 'confidence': 1.0,
                 'gates_passed': True,
                 'metadata': {'model': 'rule_based_intent'},
                 'conversation_turns': 1,
                 'memory_used': {'total_memories': 0}
             }
        
        # ================================================================
        # STEP 2: Session management
        # ================================================================
        # ================================================================
        # STEP 2: Session management
        # ================================================================
        # Treat 'default' or empty string as no session
        if not session_id or session_id == 'default':
            # Try to recover last active session for this user first
            existing_sessions = await self.conversation.get_user_sessions(str(user_id))
            if existing_sessions:
                session_id = existing_sessions[0]
                print(f"[AGENT] Step 2: Resumed last active session {session_id}")
            else:
                session_id = await self.conversation.create_session(str(user_id))
                print(f"[AGENT] Step 2: Created new session {session_id}")
        else:
            print(f"[AGENT] Step 2: Continuing session {session_id}")
        
        # Store user message in conversation history
        await self.conversation.add_message(session_id, 'user', query)
        
        # ================================================================
        # STEP 3: Memory retrieval
        # ================================================================
        memory_context = await self.memory.get_user_memories(user_id)
        episodic_count = len(memory_context.get('episodic', []))
        semantic_count = len(memory_context.get('semantic', []))
        total_memories = episodic_count + semantic_count
        
        self.stats['memories_used'] += total_memories
        
        print(f"[AGENT] Step 3: Retrieved {episodic_count} episodic + {semantic_count} semantic = {total_memories} memories")
        
        # ================================================================
        # STEP 4: Conversation history retrieval
        # ================================================================
        conversation_history = await self.conversation.build_context_from_history(
            session_id,
            max_messages=6  # Last 3 turns (3 user + 3 assistant messages)
        )
        print(f"[AGENT] Step 4: Retrieved {len(conversation_history)} messages from conversation history")
        
        # ================================================================
        # STEP 5: Context reconstruction
        # ================================================================
        reconstructed_context = self._reconstruct_context(
            normalized_query,
            memory_context,
            conversation_history
        )
        print(f"[AGENT] Step 5: Context reconstructed for LLM")
        
        # ================================================================
        # STEP 6: Model reasoning (Phi-3.5 proposes)
        # ================================================================
        proposed_response = self.phi3.process({
            'query': normalized_query,
            'context': reconstructed_context,
            'max_length': 400,
            'temperature': 0.7
        })
        print(f"[AGENT] Step 6: Phi-3.5 proposed response")
        
        # ================================================================
        # STEP 7: Controller gating
        # ================================================================
        gate_result = self.gating.validate(
            response=proposed_response['result'],
            memory_context=memory_context,
            query=normalized_query
        )
        
        passed_gates = gate_result['passed']
        print(f"[AGENT] Step 7: Gates {'PASSED ✅' if passed_gates else 'FAILED ❌'}")
        
        if not passed_gates:
            self.stats['failed_gates'] += 1
            print(f"[AGENT] Failed gates: {gate_result['failed_gates']}")
            final_response = gate_result['modified_response']
        else:
            self.stats['successful_turns'] += 1
            final_response = proposed_response['result']
        
        # ================================================================
        # STEP 8: Response delivery + storage
        # ================================================================
        response_obj = {
            'response': final_response,
            'session_id': session_id,
            'confidence': proposed_response['confidence'],
            'memory_used': {
                'episodic_count': episodic_count,
                'semantic_count': semantic_count,
                'total_memories': total_memories
            },
            'conversation_turns': len(conversation_history) // 2,  # Pairs of messages
            'gates_passed': passed_gates,
            'failed_gates': gate_result.get('failed_gates', []) if not passed_gates else [],
            'metadata': {
                'latency_seconds': proposed_response.get('metadata', {}).get('latency_seconds'),
                'model': proposed_response.get('metadata', {}).get('model', 'budget-bandhu'),
                'timestamp': datetime.now().isoformat(),
                'tokens_generated': proposed_response.get('metadata', {}).get('tokens_generated')
            }
        }
        
        # Store assistant message in conversation history
        await self.conversation.add_message(
            session_id,
            'assistant',
            final_response,
            confidence=proposed_response['confidence'],
            metadata=response_obj['metadata']
        )
        
        print(f"[AGENT] Step 8: Response delivered and stored")
        
        # ================================================================
        # STEP 9: Observation & learning evaluation
        # ================================================================
        observation = self._observe_interaction(user_id, query, response_obj)
        await self._evaluate_learning(user_id, observation, memory_context)
        print(f"[AGENT] Step 9: Observation & learning complete")
        
        print(f"[AGENT] ===== TURN COMPLETE =====\n")
        return response_obj
        
        print(f"[AGENT] ===== TURN COMPLETE =====\n")
        return response_obj
    
    def _normalize_input(self, query: str) -> str:
        """
        Clean and normalize user input.
        
        Operations:
        - Remove extra whitespace
        - Strip leading/trailing spaces
        - Basic sanitization
        
        Args:
            query: Raw user input
        
        Returns:
            Normalized query string
        """
        # Remove extra whitespace
        normalized = " ".join(query.split())
        
        # Strip and return
        return normalized.strip()
    
    def _reconstruct_context(
        self,
        query: str,
        memory_context: Dict,
        conversation_history: List[Dict]
    ) -> Dict:
        """
        Enhanced context reconstruction with conversation history.
        
        Combines multiple context sources:
        1. User query (current input)
        2. Episodic memory (events/transactions from DB)
        3. Semantic memory (user profile/facts from DB)
        4. Conversation history (last N turns from current session)
        
        This is the RAG reconstruction step that builds the full context
        for the LLM to generate a response.
        
        Args:
            query: Normalized user query
            memory_context: Dict with 'episodic' and 'semantic' lists
            conversation_history: List of previous messages in session
        
        Returns:
            Reconstructed context dict for RAG prompt building
        """
        return {
            'query': query,
            'episodic': memory_context.get('episodic', []),
            'semantic': memory_context.get('semantic', []),
            'conversation_history': conversation_history
        }
    
    def _observe_interaction(
        self,
        user_id: int,
        query: str,
        response: Dict
    ) -> Dict:
        """
        Log interaction for potential learning.
        
        Creates observation object that tracks:
        - User query and system response
        - Confidence and gate results
        - Timestamp and user ID
        - Friction detection placeholder
        
        Args:
            user_id: User identifier
            query: User's query
            response: System response object
        
        Returns:
            Observation object for learning evaluation
        """
        return {
            'user_id': user_id,
            'query': query,
            'response': response,
            'timestamp': datetime.now().isoformat(),
            'friction_detected': False,  # Updated via user feedback API
            'gates_passed': response['gates_passed']
        }
    
    async def _evaluate_learning(
        self,
        user_id: str,
        observation: Dict,
        memory_context: Dict
    ):
        """
        Learning evaluation - CONSERVATIVE and DELAYED.
        
        Only store episodic memory if:
        1. Explicit friction detected (user correction, ignored advice)
        2. Repetition confirmed (same query multiple times)
        3. Pattern identified (behavioral insights)
        
        NO INSTANT LEARNING - requires validation.
        
        Args:
            user_id: User identifier
            observation: Interaction observation object
            memory_context: Current memory context
        """
        # Check for friction signals
        if observation.get('friction_detected'):
            # Store episodic memory for corrections
            await self.memory.store_episodic_memory(
                user_id,
                event_summary=f"User correction on query: {observation['query'][:50]}",
                trigger_type='correction',
                metadata={
                    'friction': True,
                    'original_response': observation['response']['response'][:100]
                }
            )
            print(f"[AGENT] Learning: Stored episodic memory due to friction")
        
        # --- ENABLE ACTIVE LEARNING ---
        
        query_lower = observation['query'].lower()
        
        # 1. Semantic Extraction: Salary / Income
        if "salary" in query_lower or "income" in query_lower:
            match = re.search(r"(salary|income)\s+(?:is|of)?\s+(\d+(?:k|000)?)", query_lower)
            if match:
                value = match.group(2)
                await self.memory.store_semantic_memory(
                    user_id,
                    attribute_type="income",
                    value=value,
                    confidence=0.9
                )
                print(f"[AGENT] Learning: Stored semantic memory (Income: {value})")

        # 2. Episodic Extraction: Significant Purchases (> 10k)
        # We already store transactions in DB, but let's store "Major Events" in memory
        match = re.search(r"(spent|bought|paid|kharch)\s+(?:a\s+)?(.+?)\s+(?:on|for)\s+(.+)", query_lower)
        if match:
             amount_str = match.group(2).strip()
             item = match.group(3).strip()
             amount = self._parse_indian_amount(amount_str)
             
             if amount and amount > 10000: # Only significant events > 10k
                 await self.memory.store_episodic_memory(
                     user_id,
                     event_summary=f"Major Purchase: {item.title()} for ₹{amount}",
                     trigger_type='large_expense',
                     metadata={'amount': amount, 'item': item}
                 )
                 print(f"[AGENT] Learning: Stored episodic memory (Major Expense)")

        # Check for gate failures (potential learning opportunity)
        if not observation.get('gates_passed'):
            print(f"[AGENT] Learning: Gate failure recorded for future analysis")
    
    def get_session_summary(self, session_id: str) -> Dict:
        """
        Get summary of conversation session.
        
        Useful for:
        - Analytics and debugging
        - Session review
        - User history display
        
        Args:
            session_id: Conversation session identifier
        
        Returns:
            {
                'session_id': str,
                'total_messages': int,
                'total_turns': int,
                'started_at': str (ISO timestamp),
                'last_activity': str (ISO timestamp),
                'messages': List[Dict]
            }
        """
        history = self.conversation.get_conversation_history(session_id)
        
        return {
            'session_id': session_id,
            'total_messages': len(history),
            'total_turns': len(history) // 2,
            'started_at': history[0]['timestamp'] if history else None,
            'last_activity': history[-1]['timestamp'] if history else None,
            'messages': history
        }
    
    def end_session(self, session_id: str):
        """
        Mark a conversation session as ended.
        
        Args:
            session_id: Session to end
        """
        self.conversation.end_session(session_id)
        print(f"[AGENT] Session {session_id} ended")
    
    def get_stats(self) -> Dict:
        """
        Get agent performance statistics.
        
        Returns:
            {
                'total_turns': int,
                'successful_turns': int,
                'failed_gates': int,
                'success_rate': float,
                'memories_used': int,
                'avg_memories_per_turn': float
            }
        """
        total = self.stats['total_turns']
        
        return {
            'total_turns': total,
            'successful_turns': self.stats['successful_turns'],
            'failed_gates': self.stats['failed_gates'],
            'success_rate': self.stats['successful_turns'] / max(total, 1),
            'memories_used': self.stats['memories_used'],
        }

    def _parse_indian_amount(self, amount_str: str) -> Optional[float]:
        """
        Parse Indian number formats like:
        - "5000", "50.5" (numeric)
        - "50k", "50K" (thousands)
        - "1 lakh", "a lakh", "1.5 lakh", "one lakh" (lakhs)
        - "2 crore", "2.5 crores" (crores)
        """
        amount_str = amount_str.lower().strip()
        
        # Direct number
        try:
            return float(amount_str)
        except ValueError:
            pass
        
        # Multiplier patterns
        multipliers = {
            'k': 1000,
            'thousand': 1000,
            'lakh': 100000,
            'lakhs': 100000,
            'lac': 100000,
            'crore': 10000000,
            'crores': 10000000,
            'cr': 10000000,
        }
        
        # Word to number mapping
        word_to_num = {
            'a': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'half': 0.5
        }
        
        # Try patterns like "50k", "100K"
        match = re.match(r'^(\d+(?:\.\d+)?)\s*(k|thousand|lakh|lakhs|lac|crore|crores|cr)s?$', amount_str)
        if match:
            num = float(match.group(1))
            unit = match.group(2)
            return num * multipliers.get(unit, 1)
        
        # Try patterns like "a lakh", "one lakh", "1 lakh", "1.5 lakh"
        match = re.match(r'^(a|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|cr|k|thousand)s?$', amount_str)
        if match:
            num_part = match.group(1)
            unit = match.group(2)
            
            if num_part in word_to_num:
                num = word_to_num[num_part]
            else:
                try:
                    num = float(num_part)
                except ValueError:
                    return None
            
            return num * multipliers.get(unit, 1)
        
        return None

    async def _check_intent_and_execute(self, user_id: str, query: str) -> Optional[str]:
        """
        Rule-based intent detection for critical actions like Adding Transactions.
        Routes through full ML pipeline for proper categorization and anomaly detection.
        """
        # Enhanced Transaction Pattern: "spent 5000 on swiggy" or "spent a lakh on gpu"
        # Now supports: numeric, "50k", "a lakh", "2 crore", etc.
        # Also supports Hinglish: "kharch kiye", "bhare", "diye", "liya"
        match = re.search(r"(spent|paid|bought|kharch|bhare|diye|liya)\s+(?:kiye)?\s*(.+?)\s+(?:on|for|at|par|pe)?\s+(.+)", query.lower())
        if match:
             try:
                 # Group 2 is amount or merchant depending on order
                 part1 = match.group(2).strip()
                 part2 = match.group(3).strip()
                 
                 # Check which part is the amount
                 amount = self._parse_indian_amount(part1)
                 merchant = part2
                 
                 # Swap if amount is in the second part (e.g. "swiggy par 500 kharch")
                 if amount is None:
                    amount = self._parse_indian_amount(part2)
                    merchant = part1
                 
                 if amount is None or amount <= 0:
                     return None  # Could not parse amount

                 
                 if not merchant: return None # Strict check
                 
                 db = Database.get_db()
                 if Database.client is None: return None

                 # Import the ML pipeline from transactions route
                 from api.routes.transactions import process_through_ml_pipeline, update_budget_spent
                 
                 # Prepare transaction for ML pipeline
                 txn_dict = {
                     "date": datetime.now().isoformat(),
                     "amount": amount,
                     "description": merchant.title(),
                     "type": "debit"
                 }
                 
                 # Get user history for better anomaly detection
                 user_history = await db["transactions"].find(
                     {"user_id": user_id},
                     {"amount": 1, "category": 1, "date": 1, "description": 1}
                 ).sort("date", -1).limit(100).to_list(length=100)
                 
                 # Run through FULL ML pipeline (Categorization + Anomaly Detection)
                 enriched, cat_stats, anomaly_stats = await process_through_ml_pipeline(
                     [txn_dict], 
                     user_id=user_id, 
                     user_history=user_history
                 )
                 enriched_txn = enriched[0]
                 
                 # Build final document with all ML enrichments
                 doc = {
                     "user_id": user_id,
                     "amount": amount,
                     "description": merchant.title(),
                     "category": enriched_txn.get("category", "Other"),
                     "category_confidence": enriched_txn.get("category_confidence", enriched_txn.get("confidence", 0.0)),
                     "categorization_method": enriched_txn.get("method", "ml"),
                     "type": "debit",
                     "source": "chat",
                     "date": datetime.now(),
                     "is_anomaly": enriched_txn.get("is_anomaly", False),
                     "anomaly_score": enriched_txn.get("anomaly_score", 0.0),
                     "anomaly_severity": enriched_txn.get("severity", "normal"),
                     "created_at": datetime.utcnow()
                 }
                 
                 await db["transactions"].insert_one(doc)
                 
                 # Update budget spent
                 await update_budget_spent(db, user_id, doc["category"], amount)
                 
                 # Build detailed response with ML pipeline info
                 category = doc["category"]
                 confidence = doc["category_confidence"]
                 method = doc["categorization_method"]
                 anomaly_score = doc["anomaly_score"]
                 severity = doc["anomaly_severity"]
                 
                 # Format amount in Indian style
                 if amount >= 10000000:  # 1 Crore+
                     amount_str = f"₹{amount/10000000:.2f} Crore"
                 elif amount >= 100000:  # 1 Lakh+
                     amount_str = f"₹{amount/100000:.2f} Lakh"
                 elif amount >= 1000:
                     amount_str = f"₹{amount/1000:.1f}K"
                 else:
                     amount_str = f"₹{amount:.0f}"
                 
                 # Build response with ML pipeline details
                 response_lines = [
                     f"✅ **Transaction Recorded**",
                     f"",
                     f"📝 **Details:**",
                     f"• Amount: {amount_str} (₹{amount:,.0f})",
                     f"• Item: {merchant.title()}",
                     f"• Category: {category}",
                     f"",
                     f"🤖 **ML Pipeline Results:**",
                     f"• Categorization: {method.upper()} method",
                     f"• Confidence: {confidence*100:.1f}%",
                     f"• Anomaly Score: {anomaly_score:.2f}",
                     f"• Severity: {severity.capitalize()}",
                 ]
                 
                 # Add anomaly warning if detected
                 if doc["is_anomaly"]:
                     response_lines.extend([
                         f"",
                         f"⚠️ **ANOMALY DETECTED!**",
                         f"This transaction appears unusual compared to your spending patterns.",
                     ])
                 
                 # Add budget impact info
                 budget = await db["budgets"].find_one({"user_id": user_id})
                 if budget:
                     for alloc in budget.get("allocations", []):
                         if alloc.get("category") == category:
                             spent = alloc.get("spent", 0) + amount
                             limit = alloc.get("amount", 0)
                             if limit > 0:
                                 pct = (spent / limit) * 100
                                 response_lines.extend([
                                     f"",
                                     f"💰 **Budget Impact ({category}):**",
                                     f"• Spent: ₹{spent:,.0f} / ₹{limit:,.0f}",
                                     f"• Usage: {pct:.1f}%",
                                 ])
                                 if pct >= 100:
                                     response_lines.append(f"• ⛔ Budget EXCEEDED!")
                                 elif pct >= 80:
                                     response_lines.append(f"• ⚠️ Approaching limit!")
                             break
                 
                 return "\n".join(response_lines)
             except Exception as e:
                 print(f"[INTENT] Error: {e}")
                 import traceback
                 traceback.print_exc()
                 return None
        return None


# ============================================================
# Backward Compatibility Wrapper
# ============================================================

class SimpleAgentController:
    """
    Simplified version for quick testing without conversation tracking.
    
    Use AgentController (above) for production with full features.
    This is a lightweight wrapper for testing individual components.
    """
    
    def __init__(
        self,
        phi3_rag: Phi3RAG,
        memory_manager: MemoryManager
    ):
        """
        Initialize simple agent (no conversation tracking).
        
        Args:
            phi3_rag: Phi-3.5 RAG component
            memory_manager: Memory operations manager
        """
        self.phi3 = phi3_rag
        self.memory = memory_manager
        
        print("[AGENT] Simple Agent Controller initialized (no conversation tracking)")
    
    def execute_turn(self, user_id: int, query: str) -> Dict:
        """
        Simple execution without session tracking.
        
        Args:
            user_id: User identifier
            query: User query
        
        Returns:
            {
                'response': str,
                'confidence': float,
                'metadata': Dict
            }
        """
        # Get memory context
        memory_context = self.memory.get_user_memories(user_id)
        
        # Generate response
        result = self.phi3.generate(
            query=query,
            context=memory_context,
            max_length=400,
            temperature=0.7
        )
        
        return {
            'response': result['result'],
            'confidence': result['confidence'],
            'metadata': result['metadata']
        }


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    # ... remaining testing code ...
    pass
