import requests

from src.config import ( 
    EVOLUTION_API_URL, 
    EVOLUTION_INSTANCE_NAME,
    EVOLUTION_AUTHENTICATION_API_KEY
)

def send_watsapp_message(number, text):
    url = f'{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}'
    headers = {
        'apikey': EVOLUTION_AUTHENTICATION_API_KEY,
        'Content-Type': 'application/json',
    }
    payload = {
        'number': number,
        'text': text,
    }
    requests.post(
        url=url,
        headers=headers,
        json=payload,
    )

