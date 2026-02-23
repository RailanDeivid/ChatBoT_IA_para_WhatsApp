import asyncio
import traceback
import redis.asyncio as redis

from src.config import REDIS_URL, BUFFER_KEY_SUFIX, DEBOUNCE_SECONDS, BUFFER_TTL
from src.integrations.evolution_api import send_whatsapp_message
from src.chains import invoke_sql_agent


redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
debounce_tasks: dict[str, asyncio.Task] = {}


def log(*args):
    print("[BUFFER]", *args, flush=True)


async def buffer_message(chat_id: str, message: str, sender_name: str = ""):
    buffer_key = f"{chat_id}{BUFFER_KEY_SUFIX}"

    await redis_client.rpush(buffer_key, message)
    await redis_client.expire(buffer_key, BUFFER_TTL)

    log(f"Mensagem adicionada ao buffer de {chat_id}: {message}")

    existing = debounce_tasks.get(chat_id)
    if existing and not existing.done():
        existing.cancel()
        log(f"Debounce resetado para {chat_id}")

    task = asyncio.create_task(handle_debounce(chat_id, sender_name))
    debounce_tasks[chat_id] = task
    log(f"Task de debounce criada para {chat_id}")


async def handle_debounce(chat_id: str, sender_name: str = ""):
    try:
        log(f"Iniciando debounce para {chat_id}")
        await asyncio.sleep(DEBOUNCE_SECONDS)

        buffer_key = f"{chat_id}{BUFFER_KEY_SUFIX}"
        messages = await redis_client.lrange(buffer_key, 0, -1)

        full_message = " ".join(messages).strip()
        if full_message:
            log(f"Enviando mensagem agrupada para {chat_id}: {full_message}")

            loop = asyncio.get_running_loop()
            ai_response = await loop.run_in_executor(
                None,
                lambda: invoke_sql_agent(message=full_message, session_id=chat_id, sender_name=sender_name),
            )

            log(f"Resposta do agente para {chat_id}: {ai_response[:100]}")

            await loop.run_in_executor(
                None, lambda: send_whatsapp_message(number=chat_id, text=ai_response)
            )

        await redis_client.delete(buffer_key)

    except asyncio.CancelledError:
        log(f"Debounce cancelado para {chat_id}")

    except Exception as e:
        log(f"ERRO no debounce para {chat_id}: {e}")
        traceback.print_exc()

    finally:
        debounce_tasks.pop(chat_id, None)
