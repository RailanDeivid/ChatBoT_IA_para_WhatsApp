import logging
import threading
import time

import pandas as pd
from mysql.connector.pooling import MySQLConnectionPool

from src.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, RETRY_MAX_ATTEMPTS, RETRY_BACKOFF_BASE, MYSQL_POOL_SIZE

logger = logging.getLogger(__name__)

_pool: MySQLConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                logger.info("Criando pool de conexões MySQL...")
                _pool = MySQLConnectionPool(
                    pool_name="bot_pool",
                    pool_size=MYSQL_POOL_SIZE,
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    use_pure=True,
                )
    return _pool


def client(sql: str) -> pd.DataFrame:
    """
    Executa uma query SQL no MySQL e retorna um DataFrame.
    Usa connection pooling e retry com backoff exponencial.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        db = _get_pool().get_connection()
        cursor = None
        try:
            cursor = db.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return pd.DataFrame(rows, columns=columns)
        except Exception as exc:
            # Erros de sintaxe SQL (1064) e acesso negado (1045) são permanentes — não adianta retry
            errno = getattr(exc, "errno", None)
            if errno in (1064, 1045, 1146) or attempt == RETRY_MAX_ATTEMPTS:
                raise
            wait = RETRY_BACKOFF_BASE ** attempt
            logger.warning("MySQL falhou (tentativa %d/%d, errno=%s): %s — retry em %.0fs", attempt, RETRY_MAX_ATTEMPTS, errno, exc, wait)
            time.sleep(wait)
        finally:
            if cursor is not None:
                cursor.close()
            db.close()
