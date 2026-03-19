import asyncio
import logging
import re

import redis.asyncio as redis

from src.config import REDIS_URL, BUFFER_KEY_SUFIX, DEBOUNCE_SECONDS, BUFFER_TTL
from src.integrations.evolution_api import send_whatsapp_message, send_whatsapp_image, send_whatsapp_document
from src.chains import route_and_invoke

_CHART_RE = re.compile(r'\[CHART:(chart:[a-f0-9]+)\|caption:([^\]]*)\]')
_EXCEL_RE = re.compile(r'\[EXCEL:(excel:[a-f0-9]+)\|caption:([^\]]*)\]')

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

            def _on_thinking():
                send_whatsapp_message(
                    number=chat_id,
                    text="Pode levar alguns minutos, mas ja vou trazer essas informacoes para voce.",
                )

            ai_response = await loop.run_in_executor(
                None,
                lambda: route_and_invoke(
                    message=full_message,
                    session_id=chat_id,
                    sender_name=sender_name,
                    on_thinking=_on_thinking,
                ),
            )

            logger.info("Resposta do agente para %s: %.100s", chat_id, ai_response)

            chart_match = _CHART_RE.search(ai_response)
            excel_match = _EXCEL_RE.search(ai_response)

            if chart_match:
                chart_key = chart_match.group(1)
                caption = chart_match.group(2)
                text_response = _CHART_RE.sub('', ai_response).strip()
                if text_response:
                    await loop.run_in_executor(
                        None, lambda: send_whatsapp_message(number=chat_id, text=text_response)
                    )
                b64 = await redis_client.get(chart_key)
                if b64:
                    await redis_client.delete(chart_key)
                    await loop.run_in_executor(
                        None, lambda: send_whatsapp_image(number=chat_id, b64=b64, caption=caption)
                    )
                else:
                    logger.warning("Chave do grafico nao encontrada no Redis: %s", chart_key)
            elif excel_match:
                excel_key = excel_match.group(1)
                filename = excel_match.group(2)
                text_response = _EXCEL_RE.sub('', ai_response).strip()
                if text_response:
                    await loop.run_in_executor(
                        None, lambda: send_whatsapp_message(number=chat_id, text=text_response)
                    )
                b64 = await redis_client.get(excel_key)
                if b64:
                    await redis_client.delete(excel_key)
                    await loop.run_in_executor(
                        None, lambda: send_whatsapp_document(number=chat_id, b64=b64, filename=filename)
                    )
                else:
                    logger.warning("Chave do Excel nao encontrada no Redis: %s", excel_key)
            else:
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
