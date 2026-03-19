import logging
import re
import threading
import time
import unicodedata
from datetime import datetime

from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI

import redis

from src.config import (
    OPENAI_API_KEY, OPENAI_MODEL_NAME, OPENAI_MODEL_TEMPERATURE, OPENAI_BASE_URL,
    SQL_AGENT_MAX_ITERATIONS, SQL_AGENT_MAX_EXECUTION_TIME,
    RAG_AGENT_MAX_ITERATIONS, RAG_AGENT_MAX_EXECUTION_TIME,
    CONVERSATION_MAX_HISTORY,
    REDIS_URL, QUERY_CACHE_TTL,
)
from src.memory import get_session_history
from src.prompts import react_prompt, rag_prompt, router_prompt, general_prompt
from src.tools.dremio_tools import DremioSalesQueryTool, DremioDeliveryQueryTool, DremioPaymentQueryTool, DremioEstornosQueryTool, DremioMetasQueryTool
from src.tools.mysql_tools import MySQLPurchasesQueryTool
from src.tools.rag_tool import RAGDocumentQueryTool
from src.tools.chart_tool import ChartTool
from src.tools.excel_tool import ExcelExportTool

logger = logging.getLogger(__name__)

_MAX_HISTORY = CONVERSATION_MAX_HISTORY
_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _cache_get(session_id: str, message: str) -> str | None:
    key = f"cache:{session_id}:{message.lower().strip()}"
    try:
        return _redis.get(key)
    except Exception:
        return None


def _cache_set(session_id: str, message: str, response: str) -> None:
    key = f"cache:{session_id}:{message.lower().strip()}"
    try:
        _redis.setex(key, QUERY_CACHE_TTL, response)
    except Exception:
        pass


def _metric_inc(key: str) -> None:
    try:
        _redis.incr(f"metrics:{key}")
    except Exception:
        pass


def _latency_bucket(elapsed: float) -> str:
    if elapsed < 5:
        return "<5s"
    if elapsed < 30:
        return "5-30s"
    if elapsed < 60:
        return "30-60s"
    return ">60s"
_DATE_WITHOUT_YEAR = re.compile(r'(?<![/\d])(\d{1,2}/\d{1,2})(?![\d/])')
_DATE_YEAR_EXTRA_DIGITS = re.compile(r'\b(\d{1,2}/\d{1,2}/)(\d{5,})\b')
_GREETING_RE = re.compile(
    r'^\s*(oi|ola|olá|eae|eai|e ai|e aí|hey|hi|hello|bom dia|boa tarde|boa noite|'
    r'tudo bem|tudo bom|tudo certo|salve|opa|fala|fala ai|boa|ok|okay)\s*[!?.,]*\s*$',
    re.IGNORECASE,
)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()

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
                    base_url=OPENAI_BASE_URL,
                    api_key=OPENAI_API_KEY,
                )
    return _model


def _get_sql_executor() -> AgentExecutor:
    global _sql_executor
    if _sql_executor is None:
        with _sql_executor_lock:
            if _sql_executor is None:
                logger.info("Inicializando agente SQL...")
                tools = [DremioSalesQueryTool(), DremioDeliveryQueryTool(), DremioPaymentQueryTool(), DremioEstornosQueryTool(), DremioMetasQueryTool(), MySQLPurchasesQueryTool(), ChartTool(), ExcelExportTool()]
                agent = create_react_agent(llm=_get_model(), tools=tools, prompt=react_prompt)
                _sql_executor = AgentExecutor(
                    agent=agent,
                    tools=tools,
                    verbose=True,
                    handle_parsing_errors=(
                        "Se nao precisar usar ferramentas, responda com: "
                        "Final Answer: [sua resposta]. Nunca responda sem usar esse formato."
                    ),
                    max_iterations=SQL_AGENT_MAX_ITERATIONS,
                    max_execution_time=SQL_AGENT_MAX_EXECUTION_TIME,
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
                    max_iterations=RAG_AGENT_MAX_ITERATIONS,
                    max_execution_time=RAG_AGENT_MAX_EXECUTION_TIME,
                )
                logger.info("Agente RAG pronto.")
    return _rag_executor


def _complete_dates(message: str) -> str:
    now = datetime.now()
    message = _DATE_YEAR_EXTRA_DIGITS.sub(lambda m: m.group(1) + m.group(2)[:4], message)

    def _fill_year(match: re.Match) -> str:
        day, month = match.group(1).split('/')
        year = now.year
        try:
            candidate = datetime(year, int(month), int(day))
            if (candidate - now).days > 30:
                year -= 1
        except ValueError:
            pass
        return f"{match.group(1)}/{year}"

    return _DATE_WITHOUT_YEAR.sub(_fill_year, message)


def _build_invoke_input(message: str, history, sender_name: str) -> dict:
    is_first_message = len(history.messages) == 0
    is_pure_greeting = bool(_GREETING_RE.match(message))

    history_text = ""
    if history.messages:
        history_text = "Historico recente da conversa (use para entender continuidade):\n"
        for msg in history.messages[-_MAX_HISTORY:]:
            role = "Usuario" if msg.type == "human" else "Assistente"
            history_text += f"{role}: {msg.content}\n"

    if is_first_message and is_pure_greeting and sender_name:
        sender_context = (
            f"Nome do usuario: {sender_name}. "
            f"Responda APENAS com: 'Ola, {sender_name}! NINOIA, assistente interno. Como posso ajudar?'"
        )
    elif is_first_message and is_pure_greeting:
        sender_context = "Responda APENAS com: 'Ola! NINOIA, assistente interno. Como posso ajudar?'"
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


_ERROR_PREFIXES = (
    "Desculpe, ocorreu um erro",
    "Desculpe, nao consegui processar",
    "Nao encontrei informacoes",
    "Desculpe, ocorreu um erro ao consultar",
    "Não consegui obter",
)


def _is_error_response(response: str) -> bool:
    return any(response.strip().startswith(p) for p in _ERROR_PREFIXES)


def _save_to_history(message: str, response: str, session_id: str) -> None:
    if _is_error_response(response):
        return
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


_VALID_CATEGORIES = ("sql", "docs", "ambos", "geral")


def _classify_intent(message: str, history_text: str = "") -> str:
    try:
        history_section = f"Historico recente:\n{history_text}\n" if history_text else ""
        result = _get_model().invoke(router_prompt.format(input=message, history=history_section))
        raw = result.content.strip().lower()

        # Grok as vezes retorna "Categoria: sql" ou "sql." ou texto extra — extrai a categoria
        for cat in _VALID_CATEGORIES:
            if cat in raw:
                return cat

        logger.warning("Router retornou categoria invalida '%s', usando 'sql'", raw)
        return "sql"
    except Exception as e:
        logger.error("Erro no router: %s — usando 'sql' como fallback", e)
        return "sql"


def invoke_sql_agent(message: str, session_id: str, sender_name: str = "") -> str:
    message = _complete_dates(message)
    response = _strip_emojis(_run_sql_agent(message, session_id, sender_name))
    _save_to_history(message, response, session_id)
    return response


def invoke_rag_agent(message: str, session_id: str, sender_name: str = "") -> str:
    response = _strip_emojis(_run_rag_agent(message, session_id, sender_name))
    _save_to_history(message, response, session_id)
    return response


def route_and_invoke(message: str, session_id: str, sender_name: str = "", on_thinking=None) -> str:
    message = _complete_dates(message)

    # Fast-path: saudações simples não precisam do router nem do agente
    if _GREETING_RE.match(message):
        logger.info("Saudacao detectada para %s — fast-path geral", session_id)
        _metric_inc("category:geral")
        response = _strip_emojis(_run_general_response(message, session_id, sender_name))
        _save_to_history(message, response, session_id)
        return response

    cached = _cache_get(session_id, message)
    if cached:
        logger.info("Cache hit para %s: %.80s", session_id, message)
        _metric_inc("cache_hits")
        return cached

    _metric_inc("requests_total")
    history = get_session_history(session_id)
    history_text = ""
    if history.messages:
        lines = []
        for msg in history.messages[-4:]:
            role = "Usuario" if msg.type == "human" else "Assistente"
            lines.append(f"{role}: {msg.content}")
        history_text = "\n".join(lines)
    category = _classify_intent(message, history_text)
    logger.info("Intencao classificada como '%s' para: %.80s", category, message)
    _metric_inc(f"category:{category}")

    if category != "geral" and on_thinking:
        try:
            on_thinking()
        except Exception as e:
            logger.warning("Falha ao enviar mensagem de espera: %s", e)

    t_start = time.time()

    if category == "sql":
        response = _run_sql_agent(message, session_id, sender_name)
        elapsed = time.time() - t_start
        logger.info("Agente SQL respondeu em %.1fs", elapsed)
        _metric_inc(f"latency:sql:{_latency_bucket(elapsed)}")
        if response.startswith("Desculpe"):
            _metric_inc("errors:sql")
    elif category == "docs":
        response = _run_rag_agent(message, session_id, sender_name)
        elapsed = time.time() - t_start
        logger.info("Agente RAG respondeu em %.1fs", elapsed)
        _metric_inc(f"latency:rag:{_latency_bucket(elapsed)}")
        if response.startswith("Desculpe") or "Nao encontrei" in response:
            _metric_inc("errors:rag")
    elif category == "ambos":
        sql_resp = _run_sql_agent(message, session_id, sender_name)
        docs_resp = _run_rag_agent(message, session_id, sender_name)
        response = f"{sql_resp}\n\n---\n\n{docs_resp}"
        elapsed = time.time() - t_start
        logger.info("Agente AMBOS respondeu em %.1fs", elapsed)
    else:  # geral
        response = _run_general_response(message, session_id, sender_name)

    response = _strip_emojis(response)

    if category != "geral" and not response.startswith("Desculpe"):
        _cache_set(session_id, message, response)

    _save_to_history(message, response, session_id)
    return response
