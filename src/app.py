# from fastapi import FastAPI, Request
# from src.evolution_api import send_watsapp_message


# app = FastAPI()

# @app.post("/webhook")
# async def webhook(request: Request):
#     data = await request.json()
#     print("Recebido no webhook:", data)
    
#     chat_id = data.get("data", {}).get("key", {}).get("remoteJid")
#     message = data.get("data", {}).get("message", {}).get("conversation")
    
#     if chat_id and message and "@g.us" not in chat_id:
#         try:
#             send_watsapp_message(
#                 number=chat_id,
#                 text="Olá, recebi sua mensagem e vou analisar. Em breve retornarei com uma resposta."
#             )
#         except Exception as e:
#             print("Erro ao enviar mensagem:", e)

#     return {"status": "ok"}

# ----------------------------------------------------------------------------------------------

from fastapi import FastAPI, Request
from src.evolution_api import send_watsapp_message

import os
from langchain import hub
from langchain.agents import create_react_agent, AgentExecutor
from langchain.prompts import PromptTemplate
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


from src.config import (
   STRING_CONEXAO,OPENAI_API_KEY,AI_SYSTEM_PROMPT,OPENAI_MODEL_NAME
)


os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY
model = ChatOpenAI(OPENAI_MODEL_NAME)
db = SQLDatabase.from_uri(STRING_CONEXAO)
toolkit = SQLDatabaseToolkit(db=db, llm=model)
system_message = hub.pull('hwchase17/react')

agent = create_react_agent(llm=model, tools=toolkit.get_tools(), prompt=system_message)
agent_executor = AgentExecutor(agent=agent, tools=toolkit.get_tools(), verbose=True)


app = FastAPI()

# Dicionário para controlar estado por chat_id
conversas = {}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Recebido no webhook:", data)

    chat_id = data.get("data", {}).get("key", {}).get("remoteJid")
    message = data.get("data", {}).get("message", {}).get("conversation")

    if chat_id and message and "@g.us" not in chat_id:
        if chat_id not in conversas:
            # Primeira mensagem: responde com saudação
            send_watsapp_message(
                number=chat_id,
                text="Qual sua dúvida, como posso te ajudar?"
            )
            # Marca que já respondeu a saudação para esse chat_id
            conversas[chat_id] = True
        else:
            # Já respondeu a saudação, processa a pergunta no agente
            try:
                prompt = AI_SYSTEM_PROMPT.format(q=message)
                output = agent_executor.invoke({"input": prompt})
                resposta = output.get('output', 'Desculpe, não consegui responder sua pergunta no momento.')
                send_watsapp_message(
                    number=chat_id,
                    text=resposta
                )
            except Exception as e:
                print("Erro ao enviar mensagem ou processar a pergunta:", e)

    return {"status": "ok"}

