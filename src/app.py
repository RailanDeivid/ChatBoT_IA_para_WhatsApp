import logging
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.message_buffer import buffer_message
from src.integrations.evolution_api import get_media_base64, send_whatsapp_message
from src.integrations.transcribe import transcribe_audio
from src.access_control import init_db, is_authorized, is_admin, authorize, revoke, unblock, delete_user, list_users, get_user_nome
from src.memory import clear_session, get_session_messages
from src.config import UNAUTHORIZED_MESSAGE, REDIS_URL, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW, EVOLUTION_AUTHENTICATION_API_KEY


class _EvolutionKey(BaseModel):
    id: Optional[str] = None
    fromMe: Optional[bool] = False
    remoteJid: Optional[str] = None


class _EvolutionMessage(BaseModel):
    conversation: Optional[str] = None
    extendedTextMessage: Optional[dict] = None
    audioMessage: Optional[dict] = None


class _EvolutionData(BaseModel):
    key: Optional[_EvolutionKey] = None
    pushName: Optional[str] = ""
    message: Optional[_EvolutionMessage] = None


class EvolutionWebhookPayload(BaseModel):
    event: Optional[str] = ""
    data: Optional[_EvolutionData] = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Banco de controle de acesso inicializado.")
    yield

app = FastAPI(lifespan=lifespan)
_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)


async def _is_rate_limited(phone: str) -> bool:
    key = f"rl:{phone}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, RATE_LIMIT_WINDOW)
    return count > RATE_LIMIT_MAX



@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    keys = await _redis.keys("metrics:*")
    raw: dict[str, int] = {}
    if keys:
        values = await _redis.mget(*keys)
        raw = {k.removeprefix("metrics:"): int(v) for k, v in zip(keys, values) if v}

    requests_total = raw.get("requests_total", 0)
    cache_hits = raw.get("cache_hits", 0)
    cache_hit_rate = round(cache_hits / requests_total * 100, 1) if requests_total else 0.0

    errors_total = sum(v for k, v in raw.items() if k.startswith("errors:"))
    error_rate = round(errors_total / requests_total * 100, 1) if requests_total else 0.0

    latency: dict[str, dict] = {}
    for agent in ("sql", "rag"):
        buckets = {b: raw.get(f"latency:{agent}:{b}", 0) for b in ("<5s", "5-30s", "30-60s", ">60s")}
        total_calls = sum(buckets.values())
        latency[agent] = {**buckets, "total_calls": total_calls}

    categories = {k.removeprefix("category:"): v for k, v in raw.items() if k.startswith("category:")}
    errors = {k.removeprefix("errors:"): v for k, v in raw.items() if k.startswith("errors:")}

    return {
        "resumo": {
            "requests_total": requests_total,
            "cache_hits": cache_hits,
            "cache_hit_rate_pct": cache_hit_rate,
            "errors_total": errors_total,
            "error_rate_pct": error_rate,
        },
        "categorias": categories,
        "latencia": latency,
        "erros": errors,
    }


def _check_admin_key(x_api_key: str | None) -> None:
    """Valida chave de API para endpoints administrativos."""
    if not x_api_key or x_api_key != EVOLUTION_AUTHENTICATION_API_KEY:
        raise HTTPException(status_code=401, detail="Chave de API invalida.")


@app.post("/limpar_cache")
async def limpar_cache(x_api_key: Optional[str] = Header(default=None)):
    """Remove todas as respostas cacheadas do Redis."""
    _check_admin_key(x_api_key)
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = await _redis.scan(cursor, match="cache:*", count=100)
        if keys:
            deleted += await _redis.delete(*keys)
        if cursor == 0:
            break
    logger.info("Cache limpo via endpoint: %d chaves removidas.", deleted)
    return {"chaves_removidas": deleted}


@app.post("/reindexar")
async def reindexar(x_api_key: Optional[str] = Header(default=None)):
    """Indexa novos arquivos da pasta rag_files sem reiniciar o servidor."""
    _check_admin_key(x_api_key)
    import asyncio
    loop = asyncio.get_running_loop()
    from src.vectorstore import reload_vectorstore
    ok, msg = await loop.run_in_executor(None, reload_vectorstore)
    logger.info("Reindexacao via endpoint: %s", msg)
    return {"sucesso": ok, "mensagem": msg}


@app.post("/webhook")
async def webhook(payload: EvolutionWebhookPayload):
    if payload.event != "messages.upsert" or not payload.data:
        return {"status": "ok"}

    data = payload.data
    key = data.key or _EvolutionKey()

    if key.fromMe:
        return {"status": "ok"}

    chat_id = key.remoteJid
    sender_name = data.pushName or ""
    msg_content = data.message or _EvolutionMessage()

    message = (
        msg_content.conversation
        or (msg_content.extendedTextMessage or {}).get("text")
    )

    # Ignora grupos
    if not chat_id or "@g.us" in chat_id:
        logger.debug("Mensagem de grupo ignorada (chat_id=%s).", chat_id)
        return {"status": "ok"}

    # Extrai só o número (remove @s.whatsapp.net)
    phone = chat_id.split("@")[0]

    # --- Controle de acesso ---
    if not is_authorized(phone):
        logger.info("Acesso negado para %s (%s)", sender_name or phone, phone)
        send_whatsapp_message(chat_id, UNAUTHORIZED_MESSAGE)
        return {"status": "ok"}

    # --- Rate limiting ---
    if await _is_rate_limited(phone):
        logger.warning("Rate limit atingido para %s", phone)
        send_whatsapp_message(chat_id, "Você está enviando mensagens muito rapidamente. Aguarde um momento.")
        return {"status": "ok"}

    # --- Comando /limpar (disponível para todos os usuários autorizados) ---
    if message and message.strip().lower() == "/limpar":
        clear_session(chat_id)
        logger.info("Historico limpo pelo usuario %s (%s).", sender_name or phone, phone)
        send_whatsapp_message(chat_id, "Historico de conversa apagado.")
        return {"status": "ok"}

    # --- Comandos admin ---
    if message and message.startswith("/"):
        if is_admin(phone):
            logger.info("[admin] Comando recebido de %s (%s): %s", sender_name or phone, phone, message.strip())
            response = _handle_admin_command(message.strip(), admin_phone=phone, sender_name=sender_name)
            if response:
                logger.info("[admin] Resposta do comando para %s: %.120s", phone, response)
                send_whatsapp_message(chat_id, response)
                return {"status": "ok"}
        else:
            logger.warning("[admin] Tentativa de comando por nao-admin %s (%s): %s", sender_name or phone, phone, message.strip())
            send_whatsapp_message(chat_id, "Comando não reconhecido.")
            return {"status": "ok"}

    # Se não tem texto mas tem áudio, transcreve com Whisper
    if not message and msg_content.audioMessage:
        audio_b64 = get_media_base64(key.model_dump())
        if audio_b64:
            message = transcribe_audio(audio_b64)
            logger.info("Áudio transcrito de %s: %.80s", sender_name or chat_id, message)

    # Ignora mensagens sem texto (sticker, imagem sem legenda, reação, etc.)
    if not message:
        logger.debug("Mensagem sem texto ignorada (chat_id=%s, tipo provavelmente midia/sticker/reacao).", chat_id)
        return {"status": "ok"}

    logger.info("Mensagem de %s: %.80s", sender_name or chat_id, message)

    await buffer_message(chat_id=chat_id, message=message, sender_name=sender_name, message_id=key.id or "")

    return {"status": "ok"}


def _handle_admin_command(message: str, admin_phone: str, sender_name: str = "") -> str | None:
    """
    Processa comandos administrativos enviados via WhatsApp.

    Comandos disponíveis:
      /autorizar 5511999999999 ; Nome ; Cargo ; Casa [; admin]
      /bloquear 5511999999999
      /desbloquear 5511999999999
      /remover 5511999999999
      /usuarios [admin]
      /reindexar
      /ajuda
    """
    parts = message.split(None, 1)  # divide em comando + resto
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/autorizar":
        return _cmd_autorizar(args, admin_phone)

    if cmd == "/bloquear":
        phone = args.strip()
        if not phone:
            return "Uso: /bloquear 5511999999999"
        return revoke(phone, revoked_by=admin_phone)

    if cmd == "/desbloquear":
        phone = args.strip()
        if not phone:
            return "Uso: /desbloquear 5511999999999"
        return unblock(phone, unblocked_by=admin_phone)

    if cmd == "/remover":
        phone = args.strip()
        if not phone:
            return "Uso: /remover 5511999999999"
        return delete_user(phone, deleted_by=admin_phone)

    if cmd == "/usuarios":
        return _cmd_usuarios(admin_only=args.strip().lower() == "admin")

    if cmd == "/historico":
        phone_arg = args.strip()
        if not phone_arg:
            return "Uso: /historico 5511999999999"
        return _cmd_historico(phone_arg)

    if cmd == "/reindexar":
        from src.vectorstore import reload_vectorstore
        ok, msg = reload_vectorstore()
        return msg

    if cmd == "/ajuda":
        return (
            "*Comandos disponíveis:*\n\n"
            "*/autorizar* 5511999 ; Nome ; Cargo ; Casa\n"
            "→ Autoriza novo usuario padrao\n\n"
            "*/autorizar* 5511999 ; Nome ; Cargo ; Casa ; admin\n"
            "→ Autoriza novo usuario como administrador\n\n"
            "*/bloquear* 5511999\n"
            "→ Bloqueia acesso de um usuario\n\n"
            "*/desbloquear* 5511999\n"
            "→ Desbloqueia um usuario\n\n"
            "*/remover* 5511999\n"
            "→ Remove usuario permanentemente\n\n"
            "*/usuarios*\n"
            "→ Lista usuarios padrao cadastrados\n\n"
            "*/usuarios admin*\n"
            "→ Lista administradores cadastrados\n\n"
            "*/historico* 5511999\n"
            "→ Exibe o historico de conversa de um usuario (ultimas 72h)\n\n"
            "*/reindexar*\n"
            "→ Indexa novos arquivos da pasta rag_files sem reiniciar\n\n"
            "*/limpar*\n"
            "→ Apaga seu historico de conversa (disponivel a todos)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "*Bases de dados disponíveis:*\n\n"
            "📊 *Vendas* — faturamento, ticket médio, fluxo de pessoas, produtos, funcionários, descontos\n\n"
            "🛵 *Delivery* — pedidos e faturamento por plataforma (iFood, Rappi, app próprio)\n\n"
            "↩️ *Estornos* — cancelamentos, devoluções e motivos por produto/funcionário\n\n"
            "🎯 *Metas* — realizado vs orçado, atingimento e delta por casa\n\n"
            "💳 *Formas de pagamento* — receita por método (PIX, cartão, dinheiro, etc.)\n\n"
            "🛒 *Compras* — pedidos de compra, fornecedores e notas fiscais de entrada\n\n"
            "📄 *Documentos internos* — políticas, procedimentos, organograma e contatos"
        )

    return None  # comando desconhecido — segue fluxo normal do bot


def _cmd_autorizar(args: str, admin_phone: str) -> str:
    """
    Formato: 5511999999999 ; Nome ; Cargo ; Casa
         ou: 5511999999999 ; Nome ; Cargo ; Casa ; admin
    """
    fields = [f.strip() for f in args.split(";")]

    if len(fields) < 4:
        return "⚠️ Uso: /autorizar 5511999999999 ; Nome ; Cargo ; Casa"

    phone_part = fields[0]
    nome  = fields[1]
    cargo = fields[2]
    casa  = fields[3]
    admin = len(fields) >= 5 and fields[4].lower() == "admin"
    added_by_nome = get_user_nome(admin_phone)

    return authorize(
        phone=phone_part,
        nome=nome,
        cargo=cargo,
        casa=casa,
        added_by_tel=admin_phone,
        added_by_nome=added_by_nome,
        admin=admin,
    )


def _cmd_historico(phone: str) -> str:
    """Retorna o histórico de conversa de um usuário (últimas 72h)."""
    session_id = f"{phone}@s.whatsapp.net"
    messages = get_session_messages(session_id)
    if not messages:
        return f"Nenhum histórico encontrado para {phone} nas últimas 72h."

    nome = get_user_nome(phone) or phone
    lines = [f"*Histórico de {nome} ({phone}):*"]
    for msg in messages:
        is_human = msg["role"] in ("human", "HumanMessage")
        prefix = "👤 *Usuário:*" if is_human else "🤖 *Assistente:*"
        content = msg["content"].strip()
        # Trunca respostas longas na última linha completa dentro do limite
        if len(content) > 300:
            truncated = content[:297]
            last_newline = truncated.rfind("\n")
            content = (truncated[:last_newline] if last_newline > 100 else truncated) + "\n_(truncado)_"
        lines.append(f"\n{prefix}\n{content}")

    return "\n".join(lines)


def _cmd_usuarios(admin_only: bool = False) -> str:
    users = list_users()
    if not users:
        return "Nenhum usuário cadastrado."

    filtered = [u for u in users if bool(u["is_admin"]) == admin_only]
    ativos   = [u for u in filtered if u["active"]]
    inativos = [u for u in filtered if not u["active"]]

    if not ativos and not inativos:
        return "Nenhum administrador cadastrado." if admin_only else "Nenhum usuário padrão cadastrado."

    titulo = "*Administradores:*" if admin_only else "*Usuários padrão:*"
    lines = [titulo]
    for u in ativos:
        linha = f"• {u['telefone']} | {u['nome']} | {u['cargo']} | {u['casa']}"
        if admin_only:
            linha += " | _admin_"
        lines.append(linha)

    if inativos:
        lines.append("\n*Bloqueados:*")
        for u in inativos:
            lines.append(f"• {u['nome']} ({u['telefone']})")

    return "\n".join(lines)
