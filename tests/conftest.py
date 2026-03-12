"""
Configura variáveis de ambiente falsas e mocks de dependências pesadas
antes de qualquer import de src/. Necessário para rodar testes fora do Docker.
"""
import os
import sys
from unittest.mock import MagicMock

# Mock de dependências que não estão instaladas no ambiente de dev local
# (estão disponíveis apenas dentro do container Docker)
for _mod in [
    "langchain_chroma",
    "chromadb",
    "langchain_community.vectorstores",
]:
    sys.modules.setdefault(_mod, MagicMock())

_FAKE_ENV = {
    "EVOLUTION_API_URL": "http://fake-evolution",
    "EVOLUTION_INSTANCE_NAME": "fake-instance",
    "AUTHENTICATION_API_KEY": "fake-api-key",
    "OPENAI_API_KEY": "fake-openai-key",
    "OPENAI_MODEL_NAME": "gpt-4o",
    "OPENAI_MODEL_TEMPERATURE": "0",
    "BOT_REDIS_URI": "redis://localhost:6379",
    "DB_USER": "fake",
    "DB_PASSWORD": "fake",
    "DB_HOST": "localhost",
    "DB_NAME": "fake_db",
    "DREMIO_HOST": "localhost",
    "DREMIO_USER": "fake",
    "DREMIO_PASSWORD": "fake",
}

for _k, _v in _FAKE_ENV.items():
    os.environ.setdefault(_k, _v)
