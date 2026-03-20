import redis as redis_lib

from langchain_community.chat_message_histories import RedisChatMessageHistory

from src.config import REDIS_URL

_SESSION_TTL = 86400  # 24 horas — sessões expiram após inatividade


def get_session_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(
        session_id=session_id,
        url=REDIS_URL,
        ttl=_SESSION_TTL,
    )


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

