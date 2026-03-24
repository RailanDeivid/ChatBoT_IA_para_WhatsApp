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
                telefone            TEXT PRIMARY KEY,
                nome                TEXT NOT NULL,
                cargo               TEXT,
                casa                TEXT,
                is_admin            INTEGER DEFAULT 0,
                active              INTEGER DEFAULT 1,
                adicionado_por      TEXT,
                adicionado_por_tel  TEXT,
                adicionado_por_nome TEXT,
                criado_em           TEXT DEFAULT (datetime('now', '-3 hours')),
                alterado_em         TEXT
            )
        """)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(authorized_users)").fetchall()]
        # garante colunas antigas
        if "casa" not in cols:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN casa TEXT")
        if "cargo" not in cols:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN cargo TEXT")
        # garante novas colunas de auditoria
        if "adicionado_por_tel" not in cols:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN adicionado_por_tel TEXT")
        if "adicionado_por_nome" not in cols:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN adicionado_por_nome TEXT")
        if "alterado_em" not in cols:
            conn.execute("ALTER TABLE authorized_users ADD COLUMN alterado_em TEXT")
        conn.commit()

    from src.config import SEED_USERS
    for user in SEED_USERS:
        _upsert_seed(user)


def _upsert_seed(user: dict) -> None:
    """Insere usuário seed se não existir; atualiza casa/cargo se estiverem vazios."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT casa, cargo FROM authorized_users WHERE telefone = ?", (user["telefone"],)
        ).fetchone()
        if not row:
            conn.execute(
                """INSERT INTO authorized_users (telefone, nome, cargo, casa, is_admin, adicionado_por, criado_em)
                   VALUES (?, ?, ?, ?, ?, 'sistema', datetime('now', '-3 hours'))""",
                (user["telefone"], user["nome"], user["cargo"], user["casa"], user["is_admin"]),
            )
            logger.info("Usuário seed inserido: %s (%s)", user["nome"], user["telefone"])
        else:
            # recupera casa/cargo perdidos por migration anterior
            updates = {}
            if not row["casa"]:
                updates["casa"] = user["casa"]
            if not row["cargo"]:
                updates["cargo"] = user["cargo"]
            if updates:
                sets = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE authorized_users SET {sets} WHERE telefone=?",
                    (*updates.values(), user["telefone"]),
                )
                logger.info("Usuário seed atualizado: %s (%s)", user["nome"], user["telefone"])
        conn.commit()


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
            "SELECT telefone, nome, cargo, casa, is_admin, active FROM authorized_users ORDER BY nome"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Mutações (usadas pelos comandos admin via WhatsApp)
# ---------------------------------------------------------------------------

def get_user_nome(phone: str) -> str:
    """Retorna o nome do usuário pelo telefone, ou o próprio telefone se não encontrado."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT nome FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()
    return row["nome"] if row else phone


def authorize(phone: str, nome: str, cargo: str, casa: str, added_by_tel: str, added_by_nome: str = "", admin: bool = False) -> str:
    """Adiciona ou reativa um usuário. Retorna mensagem de feedback."""
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE authorized_users
                   SET nome=?, cargo=?, casa=?, is_admin=?, active=1,
                       adicionado_por=?, adicionado_por_tel=?, adicionado_por_nome=?,
                       alterado_em=datetime('now', '-3 hours')
                   WHERE telefone=?""",
                (nome, cargo, casa, int(admin), added_by_tel, added_by_tel, added_by_nome, phone),
            )
            action = "reativado"
        else:
            conn.execute(
                """INSERT INTO authorized_users
                       (telefone, nome, cargo, casa, is_admin, adicionado_por,
                        adicionado_por_tel, adicionado_por_nome, criado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-3 hours'))""",
                (phone, nome, cargo, casa, int(admin), added_by_tel, added_by_tel, added_by_nome),
            )
            action = "autorizado"
        conn.commit()

    logger.info("Usuário %s (%s) %s por %s", nome, phone, action, added_by_tel)
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
            "UPDATE authorized_users SET active=0, alterado_em=datetime('now', '-3 hours') WHERE telefone=?",
            (phone,)
        )
        conn.commit()

    logger.info("Usuário %s bloqueado por %s", phone, revoked_by)
    return f"🚫 {row['nome']} ({phone}) bloqueado com sucesso."


def unblock(phone: str, unblocked_by: str) -> str:
    """Reativa um usuário bloqueado sem alterar seus dados. Retorna mensagem de feedback."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT nome, active FROM authorized_users WHERE telefone = ?", (phone,)
        ).fetchone()

        if not row:
            return f"⚠️ Número {phone} não encontrado."
        if row["active"]:
            return f"⚠️ {row['nome']} já está ativo."

        conn.execute(
            "UPDATE authorized_users SET active=1, alterado_em=datetime('now', '-3 hours') WHERE telefone=?",
            (phone,)
        )
        conn.commit()

    logger.info("Usuário %s desbloqueado por %s", phone, unblocked_by)
    return f"✅ {row['nome']} ({phone}) desbloqueado com sucesso."


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
