import logging

from fastapi import FastAPI, Request

from src.message_buffer import buffer_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "ok"}

    event_type = data.get("event", "")

    if event_type != "messages.upsert":
        return {"status": "ok"}

    msg_data = data.get("data", {})

    if msg_data.get("key", {}).get("fromMe"):
        return {"status": "ok"}

    chat_id = msg_data.get("key", {}).get("remoteJid")
    sender_name = msg_data.get("pushName", "")

    msg_content = msg_data.get("message", {})
    message = (
        msg_content.get("conversation")
        or msg_content.get("extendedTextMessage", {}).get("text")
    )

    # Ignora grupos e mensagens sem texto (mídia, sticker, reação, etc.)
    if not chat_id or not message or "@g.us" in chat_id:
        return {"status": "ok"}

    logger.info("Mensagem de %s: %.80s", sender_name or chat_id, message)

    await buffer_message(chat_id=chat_id, message=message, sender_name=sender_name)

    return {"status": "ok"}
