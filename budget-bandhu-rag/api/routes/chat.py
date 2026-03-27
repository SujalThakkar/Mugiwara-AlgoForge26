"""
Chat API Route
Exposes agentic conversational endpoint. (Fixed for Core Agent Compatibility)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime

# Will be initialized in main.py
router = APIRouter(prefix="/api/v1", tags=["chat"])

# Placeholder for agent controller (set in main.py)
agent_controller = None

class ChatRequest(BaseModel):
    user_id: str
    query: str
    session_id: Optional[str] = "default"
    session_context: Optional[Dict] = None

class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    confidence: float
    memory_used: Dict
    gates_passed: bool
    conversation_turns: Optional[int] = 0

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Agentic conversational endpoint.
    Executes full 9-step lifecycle.
    """
    try:
        if agent_controller is None:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        # Call Core Agent Controller
        # Core: execute_turn(user_id, query, session_id)
        result = await agent_controller.execute_turn(
            user_id=request.user_id,
            query=request.query,
            session_id=request.session_id
        )
        
        # The result from Core AgentController matches ChatResponse (mostly)
        return ChatResponse(
            response=result['response'],
            session_id=result.get('session_id'),
            confidence=result.get('confidence', 0.0),
            memory_used=result.get('memory_used', {}),
            gates_passed=result.get('gates_passed', True),
            conversation_turns=result.get('conversation_turns', 0)
        )
    
    except Exception as e:
        import traceback
        print(f"[ERROR] Chat endpoint failed: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/history/{user_id}", response_model=List[Dict])
async def get_chat_history(user_id: str):
    """Fetch conversation history for a user across all sessions"""
    try:
        from api.database import Database
        db = Database.get_db()
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")
            
        # Aggregate messages from all sessions for this user
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$messages"},
            {"$sort": {"messages.timestamp": 1}},
            {"$project": {
                "_id": 0,
                "id": "$messages.id",
                "role": "$messages.role",
                "content": "$messages.content",
                "timestamp": "$messages.timestamp",
                "type": {"$ifNull": ["$messages.type", "text"]}
            }}
        ]
        
        formatted = await db["conversations"].aggregate(pipeline).to_list(length=100)
        
        # fallback for timestamp stringification
        for msg in formatted:
            if isinstance(msg["timestamp"], datetime):
                msg["timestamp"] = msg["timestamp"].isoformat()
            
        return formatted
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] History fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def set_agent_controller(controller):
    """Called from main.py to inject agent"""
    global agent_controller
    agent_controller = controller
