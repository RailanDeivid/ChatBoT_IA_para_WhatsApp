import pandas as pd
import mysql.connector

from src.config import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
)


def client(sql, host=None, port=None, username=None, password=None, database=None):
    """
    Executa uma query SQL no MySQL e retorna um DataFrame

    Args:
        sql (str): Query SQL a ser executada
        host (str, optional): Host do MySQL. Se None, usa DB_HOST do .env
        port (int, optional): Porta do MySQL. Se None, usa DB_PORT do .env
        username (str, optional): Usuário. Se None, usa DB_USER do .env
        password (str, optional): Senha. Se None, usa DB_PASSWORD do .env
        database (str, optional): Banco de dados. Se None, usa DB_NAME do .env

    Returns:
        pd.DataFrame: Resultado da query
    """
    host = host or DB_HOST
    port = int(port or DB_PORT)
    username = username or DB_USER
    password = password or DB_PASSWORD
    database = database or DB_NAME

    if not all([host, port, username, password, database]):
        raise ValueError("Host, port, username, password e database são obrigatórios")

    db = mysql.connector.connect(
        host=host,
        port=port,
        user=username,
        password=password,
        database=database,
        use_pure=True,
    )

    cursor = db.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    cursor.close()
    db.close()

    return pd.DataFrame(rows, columns=columns)
