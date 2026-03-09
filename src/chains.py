import logging
import re
import threading
from datetime import datetime

from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI

from src.config import OPENAI_MODEL_NAME, OPENAI_MODEL_TEMPERATURE
from src.memory import get_session_history
from src.prompts import react_prompt, rag_prompt, router_prompt, general_prompt
from src.tools.dremio_tools import DremioSalesQueryTool, DremioDeliveryQueryTool, DremioPaymentQueryTool
from src.tools.mysql_tools import MySQLPurchasesQueryTool
from src.tools.rag_tool import RAGDocumentQueryTool

logger = logging.getLogger(__name__)

_MAX_HISTORY = 5
_DATE_WITHOUT_YEAR = re.compile(r'\b(\d{1,2}/\d{1,2})(?!/\d)')
_DATE_YEAR_EXTRA_DIGITS = re.compile(r'\b(\d{1,2}/\d{1,2}/)(\d{5,})\b')

_model: ChatOpenAI | None = None
_model_lock = threading.Lock()

_sql_executor: AgentExecutor | None = None
_sql_executor_lock = threading.Lock()

_rag_executor: AgentExecutor | None = None
_rag_executor_lock = threading.Lock()


def _get_model() -> ChatOpenAI:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = ChatOpenAI(
                    model=OPENAI_MODEL_NAME,
                    temperature=OPENAI_MODEL_TEMPERATURE,
                )
    return _model


def _get_sql_executor() -> AgentExecutor:
    global _sql_executor
    if _sql_executor is None:
        with _sql_executor_lock:
            if _sql_executor is None:
                logger.info("Inicializando agente SQL...")
                tools = [DremioSalesQueryTool(), DremioDeliveryQueryTool(), DremioPaymentQueryTool(), MySQLPurchasesQueryTool()]
                agent = create_react_agent(llm=_get_model(), tools=tools, prompt=react_prompt)
                _sql_executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,
                    handle_parsing_errors=(
                        "Se nao precisar usar ferramentas, responda com: "
                        "Final Answer: [sua resposta]. Nunca responda sem usar esse formato."
                    ),
                    max_iterations=8,
                    max_execution_time=600,
                )
                logger.info("Agente SQL pronto.")
    return _sql_executor


def _get_rag_executor() -> AgentExecutor:
    global _rag_executor
    if _rag_executor is None:
        with _rag_executor_lock:
            if _rag_executor is None:
                logger.info("Inicializando agente RAG...")
                tools = [RAGDocumentQueryTool()]
                agent = create_react_agent(llm=_get_model(), tools=tools, prompt=rag_prompt)
                _rag_executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,
                    handle_parsing_errors=(
                        "Se nao encontrar a informacao, responda com: "
                        "Final Answer: Nao encontrei essa informacao nos documentos disponíveis."
                    ),
                    max_iterations=4,
                    max_execution_time=60,
                )
                logger.info("Agente RAG pronto.")
    return _rag_executor


def _complete_dates(message: str) -> str:
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
    all_msgs = history.messages
    if len(all_msgs) > _MAX_HISTORY * 2:
        keep = all_msgs[-(_MAX_HISTORY * 2):]
        history.clear()
        for msg in keep:
            if msg.type == "human":
                history.add_user_message(msg.content)
            else:
                history.add_ai_message(msg.content)


def _save_to_history(message: str, response: str, session_id: str) -> None:
    history = get_session_history(session_id)
    history.add_user_message(message)
    history.add_ai_message(response)
    _trim_history(history)


def _run_sql_agent(message: str, session_id: str, sender_name: str) -> str:
    history = get_session_history(session_id)
    invoke_input = _build_invoke_input(message, history, sender_name)
    try:
        result = _get_sql_executor().invoke(invoke_input)
        output = result.get('output', '')
        if not output or 'Agent stopped' in output or 'iteration limit' in output.lower():
            logger.warning("Agente SQL parou por limite. Output: %r", output)
            return 'Desculpe, nao consegui processar sua pergunta a tempo. Tente reformular ou seja mais especifico.'
        return output
    except Exception as e:
        logger.error("Erro no agente SQL: %s", e)
        return 'Desculpe, ocorreu um erro ao processar sua pergunta.'


def _run_rag_agent(message: str, session_id: str, sender_name: str) -> str:
    history = get_session_history(session_id)
    invoke_input = _build_invoke_input(message, history, sender_name)
    try:
        result = _get_rag_executor().invoke(invoke_input)
        output = result.get('output', '')
        if not output or 'Agent stopped' in output:
            logger.warning("Agente RAG parou por limite. Output: %r", output)
            return 'Nao encontrei informacoes nos documentos disponíveis.'
        return output
    except Exception as e:
        logger.error("Erro no agente RAG: %s", e)
        return 'Desculpe, ocorreu um erro ao consultar os documentos.'


def _run_general_response(message: str, session_id: str, sender_name: str) -> str:
    history = get_session_history(session_id)
    invoke_input = _build_invoke_input(message, history, sender_name)
    try:
        prompt_text = general_prompt.format(**invoke_input)
        result = _get_model().invoke(prompt_text)
        return result.content
    except Exception as e:
        logger.error("Erro na resposta geral: %s", e)
        return "Olá! Como posso ajudar?"


def _classify_intent(message: str) -> str:
    try:
        result = _get_model().invoke(router_prompt.format(input=message))
        category = result.content.strip().lower()
        if category not in ("sql", "docs", "ambos", "geral"):
            logger.warning("Router retornou categoria invalida '%s', usando 'sql'", category)
            return "sql"
        return category
    except Exception as e:
        logger.error("Erro no router: %s — usando 'sql' como fallback", e)
        return "sql"


def invoke_sql_agent(message: str, session_id: str, sender_name: str = "") -> str:
    message = _complete_dates(message)
    response = _run_sql_agent(message, session_id, sender_name)
    _save_to_history(message, response, session_id)
    return response


def invoke_rag_agent(message: str, session_id: str, sender_name: str = "") -> str:
    response = _run_rag_agent(message, session_id, sender_name)
    _save_to_history(message, response, session_id)
    return response


def route_and_invoke(message: str, session_id: str, sender_name: str = "") -> str:
    message = _complete_dates(message)
    category = _classify_intent(message)
    logger.info("Intencao classificada como '%s' para: %.80s", category, message)

    if category == "sql":
        response = _run_sql_agent(message, session_id, sender_name)
    elif category == "docs":
        response = _run_rag_agent(message, session_id, sender_name)
    elif category == "ambos":
        sql_resp = _run_sql_agent(message, session_id, sender_name)
        docs_resp = _run_rag_agent(message, session_id, sender_name)
        response = f"{sql_resp}\n\n---\n\n{docs_resp}"
    else:  # geral
        response = _run_general_response(message, session_id, sender_name)

    _save_to_history(message, response, session_id)
    return response
