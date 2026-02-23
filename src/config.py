import os
from dotenv import load_dotenv


load_dotenv()


def _require(name: str) -> str:
    """Lança erro claro se variável de ambiente obrigatória estiver ausente."""
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Variável de ambiente obrigatória não definida: {name}")
    return value


# Evolution API
EVOLUTION_API_URL                = _require("EVOLUTION_API_URL")
EVOLUTION_INSTANCE_NAME          = _require("EVOLUTION_INSTANCE_NAME")
EVOLUTION_AUTHENTICATION_API_KEY = _require("AUTHENTICATION_API_KEY")

# OpenAI
OPENAI_API_KEY           = _require("OPENAI_API_KEY")
OPENAI_MODEL_NAME        = _require("OPENAI_MODEL_NAME")
OPENAI_MODEL_TEMPERATURE = float(_require("OPENAI_MODEL_TEMPERATURE"))

# Redis / Buffer
REDIS_URL        = _require("BOT_REDIS_URI")
BUFFER_KEY_SUFIX = os.getenv("BUFFER_KEY_SUFIX", ":buffer")
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "3"))
BUFFER_TTL       = int(os.getenv("BUFFER_TTL", "300"))

# MySQL
DB_USER     = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")
DB_HOST     = _require("DB_HOST")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_NAME     = _require("DB_NAME")

STRING_CONEXAO = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Dremio
DREMIO_HOST     = _require("DREMIO_HOST")
DREMIO_USER     = _require("DREMIO_USER")
DREMIO_PASSWORD = _require("DREMIO_PASSWORD")
