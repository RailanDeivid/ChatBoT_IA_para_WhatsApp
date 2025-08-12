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


load_dotenv()

usuario = os.getenv("DB_USER")
senha = os.getenv("DB_PASSWORD")
porta = os.getenv("DB_PORT")
nome_do_banco = os.getenv("DB_NAME")
host = os.getenv("DB_HOST")
api_key = os.getenv("OPENAI_API_KEY")
os.environ['OPENAI_API_KEY'] = api_key

string_conexao = f"mysql+pymysql://{usuario}:{senha}@{host}:{porta}/{nome_do_banco}"

model = ChatOpenAI(model='gpt-4-turbo')
db = SQLDatabase.from_uri(string_conexao)
toolkit = SQLDatabaseToolkit(db=db, llm=model)
system_message = hub.pull('hwchase17/react')

agent = create_react_agent(llm=model, tools=toolkit.get_tools(), prompt=system_message)
agent_executor = AgentExecutor(agent=agent, tools=toolkit.get_tools(), verbose=True)

prompt_template = PromptTemplate.from_template("""
Você é um especialista em compras de produtos para bares e restaurantes.

Sua tarefa é responder perguntas utilizando **apenas** as informações contidas na tabela `505 compra`.  
Não utilize nenhuma informação externa.

**Referências da tabela:**
- Período: use a coluna `D. Lançamento`.
- Nome da casa: coluna `FANTASIA`.
- Valores monetários: coluna `V. Contábil`.
- Quantidades: coluna `Q. Estoque`.
- Grupo de produtos: coluna `Grande Grupo`.
- Subgrupo de produtos: coluna `Subgrupo`.
- Nome dos produtos: coluna `Descrição Item`.

**Regras para análise:**
1. Para cálculos de valores, use apenas a coluna `V. Contábil`.
2. Para cálculos de quantidade, use apenas a coluna `Q. Estoque`.
3. Para análises por período, utilize exclusivamente a coluna `D. Lançamento`.
4. Caso a pergunta não possa ser respondida por falta de dados:
   - Se o problema for na coluna `FANTASIA`, retorne apenas as opções disponíveis dessa coluna.
   - Se o problema for na coluna `Grande Grupo`, retorne apenas as opções disponíveis dessa coluna.
   - Se o problema for na coluna `Subgrupo`, retorne apenas as opções disponíveis dessa coluna.
5. Responda sempre em português brasileiro e seja o mais preciso possível.

Pergunta: {q}
""")

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
                prompt = prompt_template.format(q=message)
                output = agent_executor.invoke({"input": prompt})
                resposta = output.get('output', 'Desculpe, não consegui responder sua pergunta no momento.')
                send_watsapp_message(
                    number=chat_id,
                    text=resposta
                )
            except Exception as e:
                print("Erro ao enviar mensagem ou processar a pergunta:", e)

    return {"status": "ok"}


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