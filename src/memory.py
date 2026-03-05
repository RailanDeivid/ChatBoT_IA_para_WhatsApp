import redis as redis_lib

from langchain_community.chat_message_histories import RedisChatMessageHistory

from src.config import REDIS_URL

_SESSION_TTL = 86400       # 24 horas — sessões expiram após inatividade
_SENT_MSGS_TTL = 6 * 86400 # 6 dias — cobre o ciclo de auto-delete de 5 dias
_SENT_MSGS_MAX = 200        # máximo de IDs armazenados por chat


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
    keys = client.keys("message_store:*")
    if keys:
        return client.delete(*keys)
    return 0


# ---------------------------------------------------------------------------
# Armazenamento de IDs de mensagens enviadas (para deleção no WhatsApp)
# ---------------------------------------------------------------------------

def store_sent_message(chat_id: str, message_id: str) -> None:
    """Armazena ID de mensagem enviada pelo bot para possível deleção futura."""
    client = redis_lib.from_url(REDIS_URL)
    key = f"sent_msgs:{chat_id}"
    client.rpush(key, message_id)
    client.ltrim(key, -_SENT_MSGS_MAX, -1)
    client.expire(key, _SENT_MSGS_TTL)


def get_all_sent_chats() -> list[str]:
    """Retorna todos os chat_ids com mensagens armazenadas."""
    client = redis_lib.from_url(REDIS_URL)
    keys = client.keys("sent_msgs:*")
    return [
        (k.decode() if isinstance(k, bytes) else k).removeprefix("sent_msgs:")
        for k in keys
    ]


def get_sent_message_ids(chat_id: str, count: int = 200) -> list[str]:
    """Retorna os últimos N IDs de mensagens enviadas pelo bot para um chat."""
    client = redis_lib.from_url(REDIS_URL)
    key = f"sent_msgs:{chat_id}"
    ids = client.lrange(key, -count, -1)
    return [mid.decode() if isinstance(mid, bytes) else mid for mid in ids]


def clear_sent_messages(chat_id: str) -> None:
    """Remove todos os IDs de mensagens armazenados para um chat."""
    client = redis_lib.from_url(REDIS_URL)
    client.delete(f"sent_msgs:{chat_id}")