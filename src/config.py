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

# RAG
RAG_FILES_DIR    = os.getenv("RAG_FILES_DIR", "rag_files")
VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "vectorstore")

# Controle de acesso
SQLITE_PATH = os.getenv("SQLITE_PATH", "data/access.db")

# Auto-delete de mensagens do WhatsApp (0 = desativado)
AUTO_DELETE_DAYS = int(os.getenv("AUTO_DELETE_DAYS", "0"))

UNAUTHORIZED_MESSAGE = os.getenv(
    "UNAUTHORIZED_MESSAGE",
    "Olá! Você não está autorizado a usar este assistente. Entre em contato com um administrador.",
)

# Usuários seed — lidos do .env, nunca hardcoded no código
# Formato: TELEFONE:NOME:SETOR:CASA:admin|user (separados por vírgula)
def _parse_seed_users(raw: str) -> list[dict]:
    users = []
    for entry in raw.split(","):
        parts = [p.strip() for p in entry.strip().split(":")]
        if len(parts) < 4:
            continue
        users.append({
            "telefone": parts[0],
            "nome":     parts[1],
            "cargo":    parts[2],
            "casa":    parts[3],
            "is_admin": 1 if len(parts) >= 5 and parts[4].lower() == "admin" else 0,
        })
    return users

SEED_USERS: list[dict] = _parse_seed_users(os.getenv("SEED_USERS", ""))
