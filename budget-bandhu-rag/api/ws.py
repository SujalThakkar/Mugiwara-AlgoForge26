import json
import asyncio
import logging
import time
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.callbacks import dispatch_custom_event

from agents.agent_graph import build_agent_graph
from models.schemas import BudgetBandhuAgentState, FinalResponse
from api.database import Database

logger = logging.getLogger("BudgetBandhu.WS")

router = APIRouter()

# Global graph instance (lazy loaded)
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        # Use the global Database instance which is already connected in life-span
        _graph = build_agent_graph(pool=Database)
    return _graph

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent interaction.
    Input: {"user_id": str, "session_id": str, "query": str}
    Outputs: Status frames, Token frames, and FinalResponse frame.
    """
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        graph = get_graph()
        
        while True:
            # Receive query
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON payload"})
                continue

            user_id = data.get("user_id")
            session_id = data.get("session_id", str(uuid.uuid4()))
            query = data.get("query")

            if not user_id or not query:
                await websocket.send_json({"error": "Missing user_id or query"})
                continue

            # Initialize state
            state = BudgetBandhuAgentState(
                user_id=user_id,
                session_id=session_id,
                query=query,
                query_id=f"q_{uuid.uuid4().hex[:8]}"
            )

            start_time = time.time()
            
            try:
                # Use astream_events to catch 'status' and 'llm_token' custom events
                async for event in graph.astream_events(state, version="v2"):
                    kind = event.get("event")
                    
                    if kind == "on_custom_event":
                        event_name = event.get("name")
                        event_data = event.get("data", {})
                        
                        if event_name == "status":
                            await websocket.send_json({"status": event_data.get("status")})
                        elif event_name == "llm_token":
                            await websocket.send_json({"token": event_data.get("token")})

                    elif kind == "on_chain_end" and event.get("name") == "LangGraph":
                        # Final state capture
                        output_state = event["data"].get("output")
                        if output_state:
                            final_resp = output_state.final_response
                            if final_resp:
                                # Ensure we send the final JSON frame
                                await websocket.send_json({
                                    "final_response": {
                                        "response_text": final_resp.response_text,
                                        "confidence_tier": final_resp.confidence_tier,
                                        "confidence_score": final_resp.confidence_score,
                                        "simulation_summary": final_resp.simulation_summary,
                                        "query_intent": output_state.query_intent.value if output_state.query_intent else "UNKNOWN",
                                        "sources_used": list(output_state.memory_context.retrieval_sources.keys()) if output_state.memory_context else [],
                                        "performance": {
                                            "total_ms": int((time.time() - start_time) * 1000)
                                        }
                                    }
                                })
                                logger.info(f"[WS] Sent final response for {output_state.query_id}")

            except Exception as e:
                logger.error(f"[WS] Graph execution error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await websocket.send_json({"error": "Internal processing error", "details": str(e)})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
