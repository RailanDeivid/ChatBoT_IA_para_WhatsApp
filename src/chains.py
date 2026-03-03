import logging
import re
import threading
from datetime import datetime

from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI

from src.config import OPENAI_MODEL_NAME, OPENAI_MODEL_TEMPERATURE
from src.memory import get_session_history
from src.prompts import react_prompt
from src.tools.dremio_tools import DremioSalesQueryTool
from src.tools.mysql_tools import MySQLPurchasesQueryTool

logger = logging.getLogger(__name__)

_MAX_HISTORY = 5
_DATE_WITHOUT_YEAR = re.compile(r'\b(\d{1,2}/\d{1,2})(?!/\d)')
_DATE_YEAR_EXTRA_DIGITS = re.compile(r'\b(\d{1,2}/\d{1,2}/)(\d{5,})\b')

_executor: AgentExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                logger.info("Inicializando modelo e agente...")
                model = ChatOpenAI(
                    model=OPENAI_MODEL_NAME,
                    temperature=OPENAI_MODEL_TEMPERATURE,
                )
                tools = [DremioSalesQueryTool(), MySQLPurchasesQueryTool()]
                agent = create_react_agent(llm=model, tools=tools, prompt=react_prompt)
                _executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,
                    handle_parsing_errors=(
                        "Se nao precisar usar ferramentas, responda com: "
                        "Final Answer: [sua resposta]. Nunca responda sem usar esse formato."
                    ),
                    max_iterations=8,
                    max_execution_time=300,
                )
                logger.info("Agente pronto.")
    return _executor


def _complete_dates(message: str) -> str:
    """Completa datas sem ano e corrige anos com digitos extras."""
    year = datetime.now().year
    message = _DATE_YEAR_EXTRA_DIGITS.sub(lambda m: m.group(1) + m.group(2)[:4], message)
    return _DATE_WITHOUT_YEAR.sub(rf'\1/{year}', message)


def _build_invoke_input(message: str, history, sender_name: str) -> dict:
    is_first_message = len(history.messages) == 0

    history_text = ""
    if history.messages:
        history_text = "Historico recente da conversa (use para entender continuidade):\n"
        for msg in history.messages[-_MAX_HISTORY:]:
            role = "Usuario" if msg.type == "human" else "Assistente"
            history_text += f"{role}: {msg.content}\n"

    if sender_name and is_first_message:
        sender_context = (
            f"PRIMEIRO CONTATO. Nome do usuario no WhatsApp: {sender_name}. "
            f"Cumprimente-o pelo nome e apresente-se como NINOIA antes de responder."
        )
    elif is_first_message:
        sender_context = (
            "PRIMEIRO CONTATO. Usuario sem nome cadastrado. "
            "Cumprimente-o e apresente-se como NINOIA antes de responder."
        )
    elif sender_name:
        sender_context = f"Nome do usuario no WhatsApp: {sender_name}."
    else:
        sender_context = ""

    return {
        "input": message,
        "current_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sender_context": sender_context,
        "history": history_text,
    }


def _trim_history(history) -> None:
    """Mantém somente os últimos _MAX_HISTORY pares de mensagens no Redis."""
    all_msgs = history.messages
    if len(all_msgs) > _MAX_HISTORY * 2:
        keep = all_msgs[-(_MAX_HISTORY * 2):]
        history.clear()
        for msg in keep:
            if msg.type == "human":
                history.add_user_message(msg.content)
            else:
                history.add_ai_message(msg.content)


def invoke_sql_agent(message: str, session_id: str, sender_name: str = "") -> str:
    history = get_session_history(session_id)
    message = _complete_dates(message)
    invoke_input = _build_invoke_input(message, history, sender_name)

    try:
        result = _get_executor().invoke(invoke_input)
        output = result.get('output', '')
        if not output or 'Agent stopped' in output or 'iteration limit' in output.lower():
            logger.warning("Agente parou por limite. Output: %r", output)
            response = 'Desculpe, nao consegui processar sua pergunta a tempo. Tente reformular ou seja mais especifico.'
        else:
            response = output
    except Exception as e:
        logger.error("Erro no agente: %s", e)
        response = 'Desculpe, ocorreu um erro ao processar sua pergunta.'

    history.add_user_message(message)
    history.add_ai_message(response)
    _trim_history(history)

    return response
