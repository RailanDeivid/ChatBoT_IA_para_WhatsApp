import logging

import requests

from src.config import (
    EVOLUTION_API_URL,
    EVOLUTION_INSTANCE_NAME,
    EVOLUTION_AUTHENTICATION_API_KEY,
)

logger = logging.getLogger(__name__)

_HEADERS = {
    "apikey": EVOLUTION_AUTHENTICATION_API_KEY,
    "Content-Type": "application/json",
}


def _send_media(number: str, mediatype: str, mimetype: str, b64: str,
                caption: str = "", filename: str = "") -> None:
    """Envia mídia (imagem ou documento) via Evolution API."""
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE_NAME}"
    payload = {
        "number": number,
        "mediatype": mediatype,
        "mimetype": mimetype,
        "media": b64,
        "caption": caption,
    }
    if filename:
        payload["fileName"] = filename
    try:
        response = requests.post(url=url, json=payload, headers=_HEADERS, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("Timeout ao enviar %s para %s", mediatype, number)
    except requests.exceptions.HTTPError as e:
        logger.error("Erro HTTP ao enviar %s para %s: %s — %s", mediatype, number, e.response.status_code, e.response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao enviar %s para %s: %s", mediatype, number, e)


def send_whatsapp_message(number: str, text: str) -> str | None:
    """
    Envia mensagem de texto via Evolution API.
    Retorna o message ID se enviado com sucesso, None caso contrário.
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"
    payload = {"number": number, "text": text}
    try:
        response = requests.post(url=url, json=payload, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        return response.json().get("key", {}).get("id")
    except requests.exceptions.Timeout:
        logger.error("Timeout ao enviar mensagem para %s", number)
    except requests.exceptions.HTTPError as e:
        logger.error("Erro HTTP ao enviar para %s: %s — %s", number, e.response.status_code, e.response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao enviar mensagem para %s: %s", number, e)
    return None


def send_whatsapp_image(number: str, b64: str, caption: str = "") -> None:
    """Envia imagem PNG via Evolution API."""
    _send_media(number, "image", "image/png", b64, caption=caption)


def send_whatsapp_document(number: str, b64: str, filename: str) -> None:
    """Envia arquivo .xlsx via Evolution API."""
    _send_media(
        number, "document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        b64, caption=filename, filename=filename,
    )


def send_whatsapp_presence(number: str) -> None:
    """Envia status 'digitando...' para o usuário via Evolution API."""
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE_NAME}"
    clean_number = number.split("@")[0]
    payload = {"number": clean_number, "delay": 1500, "presence": "composing"}
    try:
        response = requests.post(url=url, json=payload, headers=_HEADERS, timeout=5)
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        logger.warning("Falha ao enviar presenca para %s: %s — body: %s", number, e, e.response.text)
    except Exception as e:
        logger.warning("Falha ao enviar presenca para %s: %s", number, e)


def send_whatsapp_reaction(number: str, message_id: str, emoji: str) -> None:
    """Envia reação a uma mensagem específica via Evolution API."""
    url = f"{EVOLUTION_API_URL}/message/sendReaction/{EVOLUTION_INSTANCE_NAME}"
    payload = {
        "key": {"remoteJid": number, "fromMe": False, "id": message_id},
        "reaction": emoji,
    }
    try:
        response = requests.post(url=url, json=payload, headers=_HEADERS, timeout=5)
        response.raise_for_status()
    except Exception as e:
        logger.debug("Falha ao reagir a mensagem %s: %s", message_id, e)


def get_media_base64(message_key: dict) -> str:
    """Baixa mídia (áudio, imagem, etc.) da Evolution API e retorna em base64."""
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE_NAME}"
    try:
        response = requests.post(
            url=url,
            json={"message": {"key": message_key}},
            headers=_HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("base64", "")
    except requests.exceptions.Timeout:
        logger.error("Timeout ao baixar mídia: %s", message_key.get("id"))
    except requests.exceptions.HTTPError as e:
        logger.error("Erro HTTP ao baixar mídia: %s — %s", e.response.status_code, e.response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao baixar mídia: %s", e)
    return ""
