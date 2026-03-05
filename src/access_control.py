import logging
import sqlite3
from pathlib import Path

from src.config import SQLITE_PATH

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Cria tabela e insere usuários iniciais se ainda não existirem."""
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                telefone    TEXT PRIMARY KEY,
                nome        TEXT NOT NULL,
                setor       TEXT,
                casa        TEXT,
                is_admin    INTEGER DEFAULT 0,
                active      INTEGER DEFAULT 1,
                adicionado_por TEXT,
                criado_em   TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

    from src.config import SEED_USERS
    for user in SEED_USERS:
        _upsert_seed(user)


def _upsert_seed(user: dict) -> None:
    """Insere usuário seed apenas se o número ainda não existir."""
    with _get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM authorized_users WHERE telefone = ?", (user["telefone"],)
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO authorized_users (telefone, nome, setor, casa, is_admin, adicionado_por)
                   VALUES (?, ?, ?, ?, ?, 'sistema')""",
                (user["telefone"], user["nome"], user["setor"], user["casa"], user["is_admin"]),
            )
            conn.commit()
            logger.info("Usuário seed inserido: %s (%s)", user["nome"], user["telefone"])


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def is_authorized(phone: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()
    return bool(row and row["active"])


def is_admin(phone: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT is_admin, active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()
    return bool(row and row["active"] and row["is_admin"])


def list_users() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT telefone, nome, setor, casa, is_admin, active FROM authorized_users ORDER BY nome"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Mutações (usadas pelos comandos admin via WhatsApp)
# ---------------------------------------------------------------------------

def authorize(phone: str, nome: str, setor: str, casa: str, added_by: str, admin: bool = False) -> str:
    """Adiciona ou reativa um usuário. Retorna mensagem de feedback."""
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE authorized_users
                   SET nome=?, setor=?, casa=?, is_admin=?, active=1, adicionado_por=?
                   WHERE telefone=?""",
                (nome, setor, casa, int(admin), added_by, phone),
            )
            action = "reativado"
        else:
            conn.execute(
                """INSERT INTO authorized_users (telefone, nome, setor, casa, is_admin, adicionado_por)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (phone, nome, setor, casa, int(admin), added_by),
            )
            action = "autorizado"
        conn.commit()

    logger.info("Usuário %s (%s) %s por %s", nome, phone, action, added_by)
    return f"✅ {nome} ({phone}) {action} com sucesso."


def revoke(phone: str, revoked_by: str) -> str:
    """Desativa um usuário. Retorna mensagem de feedback."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT nome, active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()

        if not row:
            return f"⚠️ Número {phone} não encontrado."
        if not row["active"]:
            return f"⚠️ {row['nome']} já estava bloqueado."

        conn.execute(
            "UPDATE authorized_users SET active=0 WHERE telefone=?", (phone,)
        )
        conn.commit()

    logger.info("Usuário %s bloqueado por %s", phone, revoked_by)
    return f"🚫 {row['nome']} ({phone}) bloqueado com sucesso."


def delete_user(phone: str, deleted_by: str) -> str:
    """Remove permanentemente um usuário. Retorna mensagem de feedback."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT nome FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()

        if not row:
            return f"⚠️ Número {phone} não encontrado."

        conn.execute("DELETE FROM authorized_users WHERE telefone=?", (phone,))
        conn.commit()

    logger.info("Usuário %s removido permanentemente por %s", phone, deleted_by)
    return f"🗑️ {row['nome']} ({phone}) removido permanentemente."
