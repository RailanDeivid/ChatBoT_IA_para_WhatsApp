import logging

import requests

from src.config import (
    EVOLUTION_API_URL,
    EVOLUTION_INSTANCE_NAME,
    EVOLUTION_AUTHENTICATION_API_KEY,
)

logger = logging.getLogger(__name__)



def send_whatsapp_message(number: str, text: str) -> str | None:
    """
    Envia mensagem de texto via Evolution API.
    Retorna o message ID se enviado com sucesso, None caso contrário.
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_AUTHENTICATION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"number": number, "text": text}

    try:
        response = requests.post(url=url, json=payload, headers=headers, timeout=15)
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
    """Envia imagem via Evolution API usando base64."""
    url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_AUTHENTICATION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "number": number,
        "mediatype": "image",
        "mimetype": "image/png",
        "media": b64,
        "caption": caption,
    }
    try:
        response = requests.post(url=url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error("Timeout ao enviar imagem para %s", number)
    except requests.exceptions.HTTPError as e:
        logger.error("Erro HTTP ao enviar imagem para %s: %s — %s", number, e.response.status_code, e.response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao enviar imagem para %s: %s", number, e)


def get_media_base64(message_key: dict) -> str:
    """Baixa mídia (áudio, imagem, etc.) da Evolution API e retorna em base64."""
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE_NAME}"
    headers = {
        "apikey": EVOLUTION_AUTHENTICATION_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            url=url,
            json={"message": {"key": message_key}},
            headers=headers,
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
