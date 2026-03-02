import logging

import requests

from src.config import (
    EVOLUTION_API_URL,
    EVOLUTION_INSTANCE_NAME,
    EVOLUTION_AUTHENTICATION_API_KEY,
)

logger = logging.getLogger(__name__)


def send_whatsapp_message(number: str, text: str) -> bool:
    """
    Envia mensagem de texto via Evolution API.
    Retorna True se enviado com sucesso, False caso contrário.
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
        return True
    except requests.exceptions.Timeout:
        logger.error("Timeout ao enviar mensagem para %s", number)
    except requests.exceptions.HTTPError as e:
        logger.error("Erro HTTP ao enviar para %s: %s — %s", number, e.response.status_code, e.response.text)
    except requests.exceptions.RequestException as e:
        logger.error("Falha ao enviar mensagem para %s: %s", number, e)

    return False
