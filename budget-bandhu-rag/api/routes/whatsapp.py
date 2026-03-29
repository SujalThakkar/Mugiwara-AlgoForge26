"""
WhatsApp Route - Twilio Webhook
Multi-Channel Support for BudgetBandhu
"""
from fastapi import APIRouter, Form, Response, BackgroundTasks, HTTPException
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import logging
from datetime import datetime
from api.database import Database

router = APIRouter(prefix="/api/chat", tags=["whatsapp"])
logger = logging.getLogger(__name__)

# Twilio Client
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "whatsapp:+14155238886")
if TWILIO_NUMBER and not TWILIO_NUMBER.startswith("whatsapp:"):
    TWILIO_NUMBER = f"whatsapp:{TWILIO_NUMBER}"


twilio_client = None
if TWILIO_SID and TWILIO_AUTH:
    try:
        twilio_client = Client(TWILIO_SID, TWILIO_AUTH)
        logger.info("[WHATSAPP] Twilio Client Initialized")
    except Exception as e:
        logger.error(f"[WHATSAPP] Client Init Failed: {e}")

agent_controller = None

def set_agent_controller(controller):
    global agent_controller
    agent_controller = controller

async def send_whatsapp(to: str, body: str):
    if not twilio_client:
        logger.warning(f"[WHATSAPP] Client not ready. Would send to {to}: {body}")
        return
    try:
        # Run in executor to avoid blocking async loop? Client is sync.
        # For simplicity, calling directly (might block slightly)
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
            
        twilio_client.messages.create(
            from_=TWILIO_NUMBER,
            body=body,
            to=to
        )
    except Exception as e:
        logger.error(f"[WHATSAPP] Send Error: {e}")

async def handle_whatsapp_message(from_number: str, body: str, num_media: int) -> str:
    """Processes message and returns the reply text"""
    try:
        db = Database.get_db()
        if db is None:
            logger.error("[WHATSAPP] Database not connected")
            return "⚠️ Database connection error. Please try again later."

        # 1. Clean Phone (Standard for this DB: preserve 91 + 10 digits to match frontend)
        raw_digits = "".join(filter(str.isdigit, from_number))
        if len(raw_digits) >= 12 and raw_digits.startswith("91"):
            phone = raw_digits[-12:] 
        else:
            phone = raw_digits[-10:] if len(raw_digits) >= 10 else raw_digits
        
        # 2. Check User
        user = await db["users"].find_one({"_id": phone})
        
        if not user:
            # Registration Logic
            # "register as Name, Age, Gender, Location"
            lower_body = body.lower().strip()
            if lower_body.startswith("register as"):
                try:
                    # Parse: register as Name, ...
                    content = body[11:].strip() # len("register as") + 1
                    parts = content.split(",")
                    name = parts[0].strip()
                    
                    if not name:
                        raise ValueError("Name empty")

                    # Create User
                    user_doc = {
                        "_id": phone,
                        "name": name,
                        "income": 50000.0, # Default
                        "currency": "INR",
                        "password_hash": "", # No password for WhatsApp only? Or auto-gen?
                        "created_at": datetime.utcnow()
                    }
                    
                    # Add default budget etc (copy logic from user.py or just basic insert)
                    # Ideally call user.register_user logic.
                    # For now, raw insert.
                    await db["users"].insert_one(user_doc)
                    
                    return f"🎉 Welcome {name}! You are successfully registered with BudgetBandhu. You can now track expenses, ask for advice, and manage your budget here!"
                except Exception as e:
                    return "⚠️ Registration format error. Please try: 'register as Name'"
            else:
                return "👋 Welcome to BudgetBandhu!\n\nIt seems you are new here. Please register by typing:\n'register as YourName'\n(Example: 'register as Aryan')"

        # 3. Chat Logic
        if agent_controller:
            # Send status?
            # await send_whatsapp(from_number, "thinking...") 
            
            result = await agent_controller.execute_turn(
                user_id=phone,
                query=body,
                session_id=f"whatsapp_{phone}"
            )
            return result["response"]
        else:
            return "⚠️ System is starting up. Please try again in a moment."
            
    except Exception as e:
        logger.error(f"[WHATSAPP] Handler Error: {e}")
        return "🚫 Sorry, I encountered an internal error."

@router.post("/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    NumMedia: int = Form(0),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Twilio Webhook for WhatsApp
    """
    resp = MessagingResponse()
    
    if not twilio_client:
        # If API client isn't ready, we MUST reply using TwiML (Synchronously)
        # This allows the user to get a reply even without TWILIO_SID/AUTH
        reply = await handle_whatsapp_message(From, Body, NumMedia)
        resp.message(reply)
        return Response(content=str(resp), media_type="application/xml")
    
    # Otherwise, respond 200 OK immediately and process in background
    background_tasks.add_task(handle_and_send_whatsapp, From, Body, NumMedia)
    return Response(content=str(resp), media_type="application/xml")

async def handle_and_send_whatsapp(from_number: str, body: str, num_media: int):
    """Bridge for background tasks when API is available"""
    reply = await handle_whatsapp_message(from_number, body, num_media)
    await send_whatsapp(from_number, reply)
