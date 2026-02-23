import pandas as pd
from mysql.connector.pooling import MySQLConnectionPool

from src.config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME


# Pool criado uma vez na inicialização — reutiliza conexões
_pool = MySQLConnectionPool(
    pool_name="bot_pool",
    pool_size=5,
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    use_pure=True,
)


def client(sql: str) -> pd.DataFrame:
    """
    Executa uma query SQL no MySQL e retorna um DataFrame.
    Usa connection pooling para eficiência.
    A conexão é sempre devolvida ao pool, mesmo em caso de erro.
    """
    db = _pool.get_connection()
    try:
        cursor = db.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        return pd.DataFrame(rows, columns=columns)
    finally:
        db.close()
