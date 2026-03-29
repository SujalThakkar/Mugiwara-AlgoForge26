import asyncio
from core.agent_controller import AgentController

async def test_queries():
    ctrl = AgentController()
    
    queries = [
        "What is my exact monthly salary?",
        "What was my latest expenditure on food?"
    ]
    
    for q in queries:
        print(f"\n--- Testing '{q}' ---")
        try:
            res = await ctrl.execute_turn(
                user_id="917558497556",
                session_id="whatsapp_917558497556",
                query=q
            )
            print(f"✅ AI Response:\n{res.get('response')}")
            print(f"✅ Context Used: {res.get('memory_used')}")
        except Exception as e:
            print(f"❌ Crashed: {e}")

if __name__ == "__main__":
    asyncio.run(test_queries())
