from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging, traceback

logger   = logging.getLogger("BudgetBandhu")
router   = APIRouter()
_ctrl    = None


def get_controller():
    global _ctrl
    if _ctrl is None:
        from core.agent_controller import AgentController
        _ctrl = AgentController()
        logger.info("[CHAT] AgentController initialized")
    return _ctrl


class ChatRequest(BaseModel):
    user_id:         str
    query:           str
    session_id:      Optional[str]            = "default"
    session_context: Optional[Dict[str, Any]] = {}


@router.post("/api/v1/chat")
async def chat(request: ChatRequest):
    try:
        result = await get_controller().execute_turn(
            user_id    = request.user_id,
            query      = request.query,
            session_id = request.session_id or "default",
            context    = request.session_context or {}
        )
        return result
    except Exception as e:
        logger.error(f"[ERROR] Chat failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
