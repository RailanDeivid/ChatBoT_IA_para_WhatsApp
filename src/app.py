import logging

from fastapi import FastAPI, Request

from src.message_buffer import buffer_message
from src.integrations.evolution_api import get_media_base64, send_whatsapp_message
from src.integrations.transcribe import transcribe_audio
from src.access_control import init_db, is_authorized, is_admin, authorize, revoke, unblock, delete_user, list_users, get_user_nome
from src.config import UNAUTHORIZED_MESSAGE

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
      /autorizar 5511999999999 Nome | Cargo | Casa
      /autorizar 5511999999999 Nome | Cargo | Casa | admin
      /bloquear 5511999999999
      /remover 5511999999999
      /usuarios
      /usuarios admin
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

    if cmd == "/desbloquear":
        phone = args.strip()
        if not phone:
            return "⚠️ Uso: /desbloquear 5511999999999"
        return unblock(phone, unblocked_by=admin_phone)

    if cmd == "/remover":
        phone = args.strip()
        if not phone:
            return "⚠️ Uso: /remover 5511999999999"
        return delete_user(phone, deleted_by=admin_phone)

    if cmd == "/usuarios":
        if args.strip().lower() == "admin":
            return _cmd_usuarios_admin()
        return _cmd_usuarios()

    if cmd == "/ajuda":
        return (
            "*Comandos disponíveis:*\n\n"
            "*/autorizar* 5511999 ; Nome ; Cargo ; Casa\n"
            "→ Autoriza um novo usuário padrão\n\n"
            "*/autorizar* 5511999 ; Nome ; Cargo ; Casa ; admin\n"
            "→ Autoriza um novo usuário como administrador\n\n"
            "*/bloquear* 5511999\n"
            "→ Bloqueia o acesso de um usuário\n\n"
            "*/desbloquear* 5511999\n"
            "→ Desbloqueia um usuário sem alterar seus dados\n\n"
            "*/remover* 5511999\n"
            "→ Remove o usuário do sistema permanentemente\n\n"
            "*/usuarios*\n"
            "→ Lista todos os usuários padrão cadastrados\n\n"
            "*/usuarios admin*\n"
            "→ Lista todos os administradores cadastrados"
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


def _cmd_usuarios() -> str:
    users = list_users()
    if not users:
        return "Nenhum usuário cadastrado."

    ativos   = [u for u in users if u["active"] and not u["is_admin"]]
    inativos = [u for u in users if not u["active"] and not u["is_admin"]]

    if not ativos and not inativos:
        return "Nenhum usuário padrão cadastrado."

    lines = ["*Usuários padrão:*"]
    for u in ativos:
        lines.append(f"• {u['telefone']} | {u['nome']} | {u['cargo']} | {u['casa']}")

    if inativos:
        lines.append("\n*Bloqueados:*")
        for u in inativos:
            lines.append(f"• {u['nome']} ({u['telefone']})")

    return "\n".join(lines)


def _cmd_usuarios_admin() -> str:
    users = list_users()
    if not users:
        return "Nenhum usuário cadastrado."

    ativos   = [u for u in users if u["active"] and u["is_admin"]]
    inativos = [u for u in users if not u["active"] and u["is_admin"]]

    if not ativos and not inativos:
        return "Nenhum administrador cadastrado."

    lines = ["*Administradores:*"]
    for u in ativos:
        lines.append(f"• {u['telefone']} | {u['nome']} | {u['cargo']} | {u['casa']} | _admin_")

    if inativos:
        lines.append("\n*Bloqueados:*")
        for u in inativos:
            lines.append(f"• {u['nome']} ({u['telefone']})")

    return "\n".join(lines)
