import asyncio
import os
import sys

# Ensure current directory is in path
sys.path.append(os.getcwd())

async def test():
    from core.agent_controller import AgentController
    ctrl = AgentController()
    
    queries = [
        "My salary is 65000",
        "i earn 40k",
        "update my income to 75000",
        "What is my salary and budget"
    ]
    
    for q in queries:
        print(f"\nQUERY: {q}")
        intent = ctrl._classify_intent(q)
        print(f"INTENT: {intent}")
        
    await ctrl.db.client.close()

if __name__ == "__main__":
    asyncio.run(test())
