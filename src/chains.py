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


print('[CHAINS] Carregando modelo e ferramentas...', flush=True)

model = ChatOpenAI(
    model=OPENAI_MODEL_NAME,
    temperature=float(OPENAI_MODEL_TEMPERATURE),
)

tools = [DremioSalesQueryTool(), MySQLPurchasesQueryTool()]

print('[CHAINS] Baixando prompt do LangChain Hub...', flush=True)
react_prompt = hub.pull('hwchase17/react')
print('[CHAINS] Prompt carregado. Criando agente...', flush=True)

agent = create_react_agent(
    llm=model,
    tools=tools,
    prompt=react_prompt,
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors="Se nao precisar usar ferramentas, responda com: Final Answer: [sua resposta]. Nunca responda sem usar esse formato.",
    max_iterations=8,
    max_execution_time=300,
)

print('[CHAINS] Agente pronto.', flush=True)


def invoke_sql_agent(message: str, session_id: str, sender_name: str = "") -> str:
    history = get_session_history(session_id)
    is_first_message = len(history.messages) == 0

    history_text = ""
    messages = history.messages
    if messages:
        history_text = "Contexto do historico recente (use apenas para continuidade, NAO reutilize respostas anteriores):\n"
        for msg in messages[-10:]:
            role = "Usuario" if msg.type == "human" else "Assistente"
            history_text += f"{role}: {msg.content}\n"
        history_text += "\n"

    if sender_name and is_first_message:
        name_context = (
            f"O nome do usuario no WhatsApp e: {sender_name}. "
            f"Esta e a PRIMEIRA mensagem dele. Cumprimente-o pelo nome com: "
            f"'Ola {sender_name}, sou o NINO IA, seu assistente inteligente! Em que posso ajudar hoje?' "
            f"e em seguida responda a pergunta dele.\n\n"
        )
    elif is_first_message:
        name_context = (
            "Esta e a PRIMEIRA mensagem do usuario e ele nao possui nome cadastrado no WhatsApp. "
            "Cumprimente-o com: 'Ola! Sou o NINO IA, seu assistente inteligente! Em que posso ajudar hoje?' "
            "e em seguida responda a pergunta dele.\n\n"
        )
    elif sender_name:
        name_context = f"O nome do usuario no WhatsApp e: {sender_name}.\n\n"
    else:
        name_context = ""

    formatted_prompt = name_context + history_text + sql_agent_prompt.format(q=message)

    try:
        result = agent_executor.invoke({'input': formatted_prompt})
        output = result.get('output', '')
        if not output or 'Agent stopped' in output or 'iteration limit' in output.lower():
            print(f"[CHAINS] Agente parou por limite. Output: {output!r}", flush=True)
            response = 'Desculpe, nao consegui processar sua pergunta a tempo. Tente reformular ou seja mais especifico.'
        else:
            response = output
    except Exception as e:
        print(f"[CHAINS] Erro no agente: {e}", flush=True)
        response = 'Desculpe, ocorreu um erro ao processar sua pergunta.'

    history.add_user_message(message)
    history.add_ai_message(response)

    return response
