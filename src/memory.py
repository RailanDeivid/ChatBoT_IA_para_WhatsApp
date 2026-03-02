from langchain_community.chat_message_histories import RedisChatMessageHistory

from src.config import REDIS_URL

_SESSION_TTL = 86400  # 24 horas — sessões expiram após inatividade


def get_session_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(
        session_id=session_id,
        url=REDIS_URL,
        ttl=_SESSION_TTL,
    )