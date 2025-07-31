import requests

from config import ( 
    EVOLUTION_API_URL, 
    EVOLUTION_INSTANCE_NAME
)

def send_watsapp_message(number, text):
    url = f'{EVOLUTION_API_URL}/massage/sendText/{EVOLUTION_INSTANCE_NAME}'