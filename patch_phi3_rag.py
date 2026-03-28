import pathlib

rag_file = pathlib.Path(r"e:\PICT Techfiesta\BudgetBandhu\budget-bandhu-rag\intelligence\phi3_rag.py")
content = rag_file.read_text(encoding="utf-8")

# Let's cleanly replace the _build_rag_prompt definition without dealing with complex regex
start_idx = content.find("    def _build_rag_prompt(self, query: str, context: dict) -> str:")
if start_idx == -1:
    print("Function not found!")
    exit(1)
    
end_idx = content.find("    def get_stats(self) -> dict:", start_idx)

new_func = """    def _fetch_knowledge_context_sync(self, query: str) -> dict:
        \"\"\"Fetch relevant knowledge chunks from MongoDB using keyword routing.\"\"\"
        result = {"chunks": [], "chunk_count": 0}
        try:
            from database.mongo_manager import db
            import pymongo
            
            # Since phi3_rag generates via requests synchronously, we might need to 
            # use a sync mongo client for this single query if the main loop isn't handling it.
            # But mongo_manager is async. Let's try calling it via a new sync client just for KB lookup.
            import os
            CONNECTION_STRING = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
            client = pymongo.MongoClient(CONNECTION_STRING)
            database = client["budget_bandhu"]
            
            from intelligence.knowledge_router import route_query_to_docs
            target_doc_ids = route_query_to_docs(query)
            
            query_filter = {"source": "india_finance"}
            if target_doc_ids:
                query_filter["document_id"] = {"$in": target_doc_ids}
                
            cursor = database["knowledge_base"].find(query_filter, {"text": 1, "_id": 0}).limit(5)
            chunks = [c["text"] for c in cursor]
            
            result["chunks"] = chunks
            result["chunk_count"] = len(chunks)
            client.close()
        except Exception as e:
            print(f"[PHI3-RAG] KB fetch non-fatal error: {e}")
        return result

    def _build_rag_prompt(self, query: str, context: dict) -> str:
        \"\"\"Build RAG-enhanced prompt with verified knowledge base grounding.\"\"\"
        kb_context = self._fetch_knowledge_context_sync(query)
        
        prompt_parts = ["<|user|>"]
        
        prompt_parts.append(
            "You are Budget Bandhu, a friendly and expert Indian financial assistant.\\n"
            "CRITICAL RULES:\\n"
            "1. ALWAYS use Indian Rupees (₹). NEVER use dollars ($) or any other currency.\\n"
            "2. Use Indian numbering: 1,00,000 = 1 Lakh, 1,00,00,000 = 1 Crore.\\n"
            "3. Answer using the VERIFIED KNOWLEDGE below for facts, figures, tax rates, and benchmarks.\\n"
            "4. NEVER invent numbers — only use figures from the KNOWLEDGE section.\\n"
            "5. If the knowledge base doesn't have the answer, say honestly that you don't have verified data on this."
        )
        
        if kb_context["chunks"]:
            prompt_parts.append("\\n=== VERIFIED INDIAN FINANCIAL KNOWLEDGE ===")
            for chunk in kb_context["chunks"]:
                prompt_parts.append(f"📚 {chunk}")
            prompt_parts.append("=== END KNOWLEDGE ===\\n")
            
        prompt_parts.append("\\n=== USER FINANCIAL DATA ===")
        has_context = False
        
        semantic_memory = context.get('semantic', [])
        if semantic_memory:
            has_context = True
            for mem in semantic_memory[:3]:
                prompt_parts.append(f"User Profile - {mem.get('attribute_type', '')}: {mem.get('value', '')}")
                
        episodic_memory = context.get('episodic', [])
        if episodic_memory:
            has_context = True
            for mem in episodic_memory[:3]:
                prompt_parts.append(f"Recent Event: {mem.get('event_summary', '')}")
                
        if not has_context:
            prompt_parts.append("No specific financial data available for this user yet.")
        prompt_parts.append("=== END DATA ===\\n")
        
        prompt_parts.append(f"Question: {query}")
        prompt_parts.append("<|end|>\\n<|assistant|>")
        
        return "\\n".join(prompt_parts)

"""

new_content = content[:start_idx] + new_func + content[end_idx:]
rag_file.write_text(new_content, encoding="utf-8")
print("Successfully patched phi3_rag.py")
