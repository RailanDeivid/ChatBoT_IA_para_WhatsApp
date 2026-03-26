import redis as redis_lib

from langchain_community.chat_message_histories import RedisChatMessageHistory

from src.config import REDIS_URL

_SESSION_TTL = 864000  # 10 dias — sessões expiram após inatividade


def get_session_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(
        session_id=session_id,
        url=REDIS_URL,
        ttl=_SESSION_TTL,
    )


def get_session_messages(session_id: str, since_ts: float | None = None) -> list[dict]:
    """Retorna as mensagens do histórico de uma sessão como lista de dicts {role, content}.

    Se ``since_ts`` for fornecido, retorna apenas mensagens com timestamp >= since_ts.
    Mensagens sem timestamp (gravadas antes dessa funcionalidade) são sempre incluídas.
    """
    import time as _time
    history = get_session_history(session_id)
    result = []
    for msg in history.messages:
        role = getattr(msg, "type", None) or msg.__class__.__name__.lower()
        ts = (msg.additional_kwargs or {}).get("timestamp")
        if since_ts is not None and ts is not None and ts < since_ts:
            continue
        result.append({"role": role, "content": msg.content})
    return result


def clear_session(session_id: str) -> None:
    """Apaga o histórico de conversa de uma sessão específica."""
    get_session_history(session_id).clear()


def clear_all_sessions() -> int:
    """Apaga todos os históricos de conversa. Retorna a quantidade de chaves removidas."""
    client = redis_lib.from_url(REDIS_URL)
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor, match="message_store:*", count=100)
        if keys:
            deleted += client.delete(*keys)
        if cursor == 0:
            break
    return deleted

