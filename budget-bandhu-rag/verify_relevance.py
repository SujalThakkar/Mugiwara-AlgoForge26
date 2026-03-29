import asyncio
from core.agent_controller import AgentController

async def test_relevance():
    print("🎯 [TEST] Verifying RAG Relevance (Mutual Funds vs FD)...")
    ctrl = AgentController()
    
    # Query that was "breaking" in the screenshot
    query = "How good are mutual funds, if compared to simple FDs"
    user_id = "917558497556"
    
    response = await ctrl.execute_turn(user_id, query)
    
    print("\n--- AI RESPONSE ---")
    print(response["response"])
    print("-------------------\n")
    
    if "food" in response["response"].lower() or "50,090" in response["response"]:
        if "mutual fund" in response["response"].lower():
            print("⚠️ Response contains food data but also mutual fund data. (Partial fix)")
        else:
            print("❌ Response is STILL breaking with irrelevant food/salary data.")
    else:
        print("✅ Response is CLEAN and focused only on Mutual Funds/FDs!")

if __name__ == '__main__':
    asyncio.run(test_relevance())
