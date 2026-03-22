"""
Telegram Route - Webhook
Multi-Channel Support for BudgetBandhu
"""
from fastapi import APIRouter, BackgroundTasks, Request
import httpx
import os
import logging
from datetime import datetime
from api.database import Database

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

agent_controller = None

def set_agent_controller(controller):
    global agent_controller
    agent_controller = controller

async def send_telegram(chat_id: int, text: str):
    if not TELEGRAM_TOKEN:
        logger.warning(f"[TELEGRAM] Token missing. Would send to {chat_id}: {text}")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown" # Or HTML
            })
            if resp.status_code != 200:
                logger.error(f"[TELEGRAM] Send Failed: {resp.text}")
    except Exception as e:
        logger.error(f"[TELEGRAM] Send Error: {e}")

async def handle_telegram_message(update: dict):
    try:
        db = Database.get_db()
        if db is None: return

        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        
        if not chat_id:
            return

        # 1. Check User by telegram_chat_id
        user = await db["users"].find_one({"telegram_chat_id": chat_id})
        
        # 2. Command Handling
        if text.startswith("/start") or text.startswith("/help"):
            welcome_msg = (
                "👋 *Welcome to BudgetBandhu!*\n\n"
                "To link your account, please register your mobile number:\n"
                "`/register <mobile_number>`\n\n"
                "Example: `/register 9876543210`"
            )
            await send_telegram(chat_id, welcome_msg)
            return
            
        if text.startswith("/register"):
            parts = text.split()
            if len(parts) < 2:
                await send_telegram(chat_id, "⚠️ Usage: `/register <mobile_number>`")
                return
            
            mobile = parts[1].strip()
            # Basic validation
            digits = "".join(filter(str.isdigit, mobile))
            if len(digits) == 10: digits = "91" + digits
            
            if len(digits) != 12:
                await send_telegram(chat_id, "⚠️ Invalid number. Please use 10-digit mobile number.")
                return

            mobile = digits
            
            # Find user with this mobile
            existing_user = await db["users"].find_one({"_id": mobile})
            
            if existing_user:
                # Link
                await db["users"].update_one(
                    {"_id": mobile},
                    {"$set": {"telegram_chat_id": chat_id}}
                )
                await send_telegram(chat_id, f"✅ Account linked to *{existing_user.get('name', 'User')}*! You can now chat.")
            else:
                # Create new user
                user_doc = {
                    "_id": mobile,
                    "name": "Telegram User",
                    "telegram_chat_id": chat_id,
                    "income": 50000.0,
                    "currency": "INR",
                    "created_at": datetime.utcnow()
                }
                try:
                    await db["users"].insert_one(user_doc)
                    await send_telegram(chat_id, f"🎉 Account created for *{mobile}*! \nTip: Update your name / profile on the web dashboard.")
                except Exception as e:
                    await send_telegram(chat_id, "⚠️ Failed to create account.")
            return

        # 3. If Not Linked
        if not user:
            await send_telegram(chat_id, "🔒 PLease register first: `/register <mobile_number>`")
            return

        # 4. Chat Logic
        if agent_controller:
            # await send_telegram(chat_id, "_Thinking..._")
            result = await agent_controller.execute_turn(
                user_id=user["_id"], # Phone number
                query=text,
                session_id=f"telegram_{chat_id}"
            )
            
            response_text = result["response"]
            # Escape markdown special chars if needed, or disable markdown. 
            # For robustness, let's keep it simple.
            await send_telegram(chat_id, response_text)
            
    except Exception as e:
        logger.error(f"[TELEGRAM] Handler Error: {e}")
        await send_telegram(chat_id, "🚫 Error processing message.")

@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    # logger.info(f"[TELEGRAM] Update: {data}")
    background_tasks.add_task(handle_telegram_message, data)
    return {"status": "ok"}
