from fastapi import FastAPI, Request

from src.message_buffer import buffer_message

app = FastAPI()


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "ok"}

    event_type = data.get("event", "")

    # Processa só mensagens de texto recebidas
    if event_type != "messages.upsert":
        return {"status": "ok"}

    msg_data = data.get("data", {})

    # Ignora mensagens enviadas pelo próprio bot
    if msg_data.get("key", {}).get("fromMe"):
        return {"status": "ok"}

    chat_id = msg_data.get("key", {}).get("remoteJid")
    message = msg_data.get("message", {}).get("conversation")
    sender_name = msg_data.get("pushName", "")

    # Ignora grupos e mensagens sem texto (mídia, sticker, reação, etc.)
    if not chat_id or not message or "@g.us" in chat_id:
        return {"status": "ok"}

    print(f"[WEBHOOK] Mensagem de {sender_name or chat_id}: {message[:80]}", flush=True)

    await buffer_message(chat_id=chat_id, message=message, sender_name=sender_name)

    return {"status": "ok"}
