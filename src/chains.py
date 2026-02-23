from langchain import hub
from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI

from src.config import (
    OPENAI_MODEL_NAME,
    OPENAI_MODEL_TEMPERATURE,
)
from src.memory import get_session_history
from src.prompts import sql_agent_prompt
from src.tools.dremio_tools import DremioSalesQueryTool
from src.tools.mysql_tools import MySQLPurchasesQueryTool


model = ChatOpenAI(
    model=OPENAI_MODEL_NAME,
    temperature=OPENAI_MODEL_TEMPERATURE,
)

tools = [DremioSalesQueryTool(), MySQLPurchasesQueryTool()]
system_message = hub.pull('hwchase17/react')

agent = create_react_agent(
    llm=model,
    tools=tools,
    prompt=system_message,
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
)


def invoke_sql_agent(message: str, session_id: str) -> str:
    history = get_session_history(session_id)

    history_text = ""
    messages = history.messages
    if messages:
        history_text = "\n\nHistorico da conversa:\n"
        for msg in messages[-10:]:
            role = "Usuario" if msg.type == "human" else "Assistente"
            history_text += f"{role}: {msg.content}\n"

    formatted_prompt = sql_agent_prompt.format(q=message) + history_text

    try:
        result = agent_executor.invoke({'input': formatted_prompt})
        response = result.get('output', 'Desculpe, nao consegui responder sua pergunta no momento.')
    except Exception as e:
        print(f"Erro no agente: {e}")
        response = 'Desculpe, ocorreu um erro ao processar sua pergunta.'

    history.add_user_message(message)
    history.add_ai_message(response)

    return response
