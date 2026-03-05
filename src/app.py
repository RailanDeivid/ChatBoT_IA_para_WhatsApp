import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request

from src.message_buffer import buffer_message
from src.integrations.evolution_api import get_media_base64, send_whatsapp_message, delete_whatsapp_message
from src.integrations.transcribe import transcribe_audio
from src.access_control import init_db, is_authorized, is_admin, authorize, revoke, delete_user, list_users
from src.memory import clear_session, clear_all_sessions, get_all_sent_chats, get_sent_message_ids, clear_sent_messages
from src.config import UNAUTHORIZED_MESSAGE, AUTO_DELETE_DAYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Banco de controle de acesso inicializado.")

    if AUTO_DELETE_DAYS > 0:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _auto_delete_whatsapp_messages,
            trigger="interval",
            days=AUTO_DELETE_DAYS,
            id="auto_delete",
        )
        scheduler.start()
        logger.info("Auto-delete de mensagens agendado a cada %d dias.", AUTO_DELETE_DAYS)


async def _auto_delete_whatsapp_messages() -> None:
    """Apaga automaticamente todas as mensagens enviadas pelo bot no WhatsApp."""
    chats = get_all_sent_chats()
    total_deleted = 0
    for chat_id in chats:
        ids = get_sent_message_ids(chat_id)
        deleted = sum(1 for mid in ids if delete_whatsapp_message(chat_id, mid))
        total_deleted += deleted
        clear_sent_messages(chat_id)
    logger.info("Auto-delete concluído: %d mensagens apagadas em %d chats.", total_deleted, len(chats))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"status": "ok"}

    event_type = data.get("event", "")

    if event_type != "messages.upsert":
        return {"status": "ok"}

    msg_data = data.get("data", {})

    if msg_data.get("key", {}).get("fromMe"):
        return {"status": "ok"}

    chat_id = msg_data.get("key", {}).get("remoteJid")
    sender_name = msg_data.get("pushName", "")

    msg_content = msg_data.get("message", {})
    message = (
        msg_content.get("conversation")
        or msg_content.get("extendedTextMessage", {}).get("text")
    )

    # Ignora grupos
    if not chat_id or "@g.us" in chat_id:
        return {"status": "ok"}

    # Extrai só o número (remove @s.whatsapp.net)
    phone = chat_id.split("@")[0]

    # --- Controle de acesso ---
    if not is_authorized(phone):
        logger.info("Acesso negado para %s (%s)", sender_name or phone, phone)
        send_whatsapp_message(chat_id, UNAUTHORIZED_MESSAGE)
        return {"status": "ok"}

    # --- Comandos admin ---
    if message and message.startswith("/"):
        if is_admin(phone):
            response = _handle_admin_command(message.strip(), admin_phone=phone)
            if response:
                send_whatsapp_message(chat_id, response)
                return {"status": "ok"}
        else:
            # Usuário normal tentando usar comando — bloqueia sem revelar nada
            send_whatsapp_message(chat_id, "Comando não reconhecido.")
            return {"status": "ok"}

    # Se não tem texto mas tem áudio, transcreve com Whisper
    if not message and msg_content.get("audioMessage"):
        audio_b64 = get_media_base64(msg_data.get("key", {}))
        if audio_b64:
            message = transcribe_audio(audio_b64)
            logger.info("Áudio transcrito de %s: %.80s", sender_name or chat_id, message)

    # Ignora mensagens sem texto (sticker, imagem sem legenda, reação, etc.)
    if not message:
        return {"status": "ok"}

    logger.info("Mensagem de %s: %.80s", sender_name or chat_id, message)

    await buffer_message(chat_id=chat_id, message=message, sender_name=sender_name)

    return {"status": "ok"}


def _handle_admin_command(message: str, admin_phone: str) -> str | None:
    """
    Processa comandos administrativos enviados via WhatsApp.

    Comandos disponíveis:
      /autorizar 5511999999999 Nome | Setor | Casa
      /autorizar 5511999999999 Nome | Setor | Casa | admin
      /bloquear 5511999999999
      /remover 5511999999999
      /limpar 5511999999999
      /limpar tudo
      /apagar redis
      /apagar mensagens
      /usuarios
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
            return "⚠️ Uso: /bloquear 5511999999999"
        return revoke(phone, revoked_by=admin_phone)

    if cmd == "/remover":
        phone = args.strip()
        if not phone:
            return "⚠️ Uso: /remover 5511999999999"
        return delete_user(phone, deleted_by=admin_phone)

    if cmd == "/limpar":
        target = args.strip().lower()
        if not target:
            return "⚠️ Uso: /limpar 5511999999999  ou  /limpar tudo"
        if target == "tudo":
            count = clear_all_sessions()
            return f"🧹 Histórico de todas as conversas apagado ({count} sessões)."
        session_id = f"{target}@s.whatsapp.net"
        clear_session(session_id)
        return f"🧹 Histórico de {target} apagado com sucesso."

    if cmd == "/apagar":
        return _cmd_apagar(args)

    if cmd == "/usuarios":
        return _cmd_usuarios()

    if cmd == "/ajuda":
        return (
            "Comandos disponíveis:\n"
            "/autorizar 5511999 Nome | Setor | Casa\n"
            "/autorizar 5511999 Nome | Setor | Casa | admin\n"
            "/bloquear 5511999\n"
            "/remover 5511999\n"
            "/limpar 5511999\n"
            "/limpar tudo\n"
            "/apagar redis\n"
            "/apagar mensagens\n"
            "/usuarios"
        )

    return None  # comando desconhecido — segue fluxo normal do bot


def _cmd_apagar(args: str) -> str:
    subcmd = args.strip().lower()

    if subcmd == "redis":
        count = clear_all_sessions()
        return f"🧹 Memória de todas as conversas apagada no Redis ({count} sessões)."

    if subcmd == "mensagens":
        chats = get_all_sent_chats()
        if not chats:
            return "⚠️ Nenhuma mensagem armazenada para apagar."
        total_deleted = 0
        for chat_id in chats:
            ids = get_sent_message_ids(chat_id)
            deleted = sum(1 for mid in ids if delete_whatsapp_message(chat_id, mid))
            total_deleted += deleted
            clear_sent_messages(chat_id)
        return f"🗑️ {total_deleted} mensagens apagadas no WhatsApp ({len(chats)} chats)."

    return "⚠️ Uso:\n/apagar redis — apaga memória de todas as conversas\n/apagar mensagens — apaga mensagens do bot no WhatsApp"


def _cmd_autorizar(args: str, admin_phone: str) -> str:
    """
    Formato: 5511999999999 Nome | Setor | Casa
         ou: 5511999999999 Nome | Setor | Casa | admin
    """
    try:
        phone_part, rest = args.split(None, 1)
    except ValueError:
        return "⚠️ Uso: /autorizar 5511999999999 Nome | Setor | Casa"

    fields = [f.strip() for f in rest.split("|")]

    if len(fields) < 3:
        return "⚠️ Uso: /autorizar 5511999999999 Nome | Setor | Casa"

    nome  = fields[0]
    setor = fields[1]
    casa  = fields[2]
    admin = len(fields) >= 4 and fields[3].lower() == "admin"

    return authorize(
        phone=phone_part.strip(),
        nome=nome,
        setor=setor,
        casa=casa,
        added_by=admin_phone,
        admin=admin,
    )


def _cmd_usuarios() -> str:
    users = list_users()
    if not users:
        return "Nenhum usuário cadastrado."

    ativos   = [u for u in users if u["active"]]
    inativos = [u for u in users if not u["active"]]

    lines = ["*Usuários autorizados:*"]
    for u in ativos:
        tag = " _(admin)_" if u["is_admin"] else ""
        lines.append(f"• {u['nome']} | {u['setor']} | {u['casa']} ({u['telefone']}){tag}")

    if inativos:
        lines.append("\n*Bloqueados:*")
        for u in inativos:
            lines.append(f"• {u['nome']} ({u['telefone']})")

    return "\n".join(lines)
