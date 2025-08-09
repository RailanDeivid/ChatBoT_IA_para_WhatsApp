from fastapi import FastAPI, Request
from src.evolution_api import send_watsapp_message

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Recebido no webhook:", data)
    
    chat_id = data.get("data", {}).get("key", {}).get("remoteJid")
    message = data.get("data", {}).get("message", {}).get("conversation")
    
    if chat_id and message and "@g.us" not in chat_id:
        try:
            send_watsapp_message(
                number=chat_id,
                text="Olá, recebi sua mensagem e vou analisar. Em breve retornarei com uma resposta."
            )
        except Exception as e:
            print("Erro ao enviar mensagem:", e)

    return {"status": "ok"}
