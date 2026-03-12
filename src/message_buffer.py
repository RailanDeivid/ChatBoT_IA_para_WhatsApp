import asyncio
import logging
import redis.asyncio as redis

from src.config import REDIS_URL, BUFFER_KEY_SUFIX, DEBOUNCE_SECONDS, BUFFER_TTL
from src.integrations.evolution_api import send_whatsapp_message
from src.chains import route_and_invoke

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
debounce_tasks: dict[str, asyncio.Task] = {}


async def buffer_message(chat_id: str, message: str, sender_name: str = "") -> None:
    buffer_key = f"{chat_id}{BUFFER_KEY_SUFIX}"

    await redis_client.rpush(buffer_key, message)
    await redis_client.expire(buffer_key, BUFFER_TTL)

    logger.info("Mensagem adicionada ao buffer de %s: %s", chat_id, message)

    existing = debounce_tasks.get(chat_id)
    if existing and not existing.done():
        existing.cancel()
        logger.debug("Debounce resetado para %s", chat_id)

    debounce_tasks[chat_id] = asyncio.create_task(handle_debounce(chat_id, sender_name))


async def handle_debounce(chat_id: str, sender_name: str = "") -> None:
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)

        buffer_key = f"{chat_id}{BUFFER_KEY_SUFIX}"
        messages = await redis_client.lrange(buffer_key, 0, -1)

        full_message = "\n".join(messages).strip()
        if full_message:
            logger.info("Enviando mensagem agrupada para %s: %s", chat_id, full_message)

            loop = asyncio.get_running_loop()
            ai_response = await loop.run_in_executor(
                None,
                lambda: route_and_invoke(message=full_message, session_id=chat_id, sender_name=sender_name),
            )

            logger.info("Resposta do agente para %s: %.100s", chat_id, ai_response)

            await loop.run_in_executor(
                None, lambda: send_whatsapp_message(number=chat_id, text=ai_response)
            )

        await redis_client.delete(buffer_key)

    except asyncio.CancelledError:
        logger.debug("Debounce cancelado para %s", chat_id)

    except Exception:
        logger.exception("ERRO no debounce para %s", chat_id)

    finally:
        if debounce_tasks.get(chat_id) is asyncio.current_task():
            debounce_tasks.pop(chat_id, None)
