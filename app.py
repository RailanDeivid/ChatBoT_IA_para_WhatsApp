from fastapi import FastAPI, Request


app = FastAPI()


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    chat_id = data.get("data").get("key").get("remoteJid")
    message = data.get("data").get("message").get("conversation")
    
    if chat_id and message and not "@g.us" in chat_id:
        print(f"FAÇA ALGO COM A MENSAGEM:!")
    
    
    return {"status": "ok"}