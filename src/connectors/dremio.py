import pandas as pd
import requests
import time

from src.config import (
    DREMIO_HOST,
    DREMIO_USER,
    DREMIO_PASSWORD
)


def client(sql, host=None, username=None, password=None):
    """
    Executa uma query SQL no Dremio e retorna um DataFrame

    Args:
        sql (str): Query SQL a ser executada
        host (str, optional): Host do Dremio. Se None, usa DREMIO_HOST do .env
        username (str, optional): Usuário. Se None, usa DREMIO_USER do .env
        password (str, optional): Senha. Se None, usa DREMIO_PASSWORD do .env

    Returns:
        pd.DataFrame: Resultado da query

    """
    host = host or DREMIO_HOST
    username = username or DREMIO_USER
    password = password or DREMIO_PASSWORD

    if not all([host, username, password]):
        raise ValueError("Host, username e password são obrigatórios")

    # Login
    url_login = f"http://{host}/apiv2/login"
    payload = {"userName": username, "password": password}
    login_res = requests.post(url_login, json=payload)
    token = login_res.json().get("token")
    headers = {"Authorization": f"_dremio{token}"}

    # Executar query
    sql_res = requests.post(
        f"http://{host}/api/v3/sql",
        headers=headers,
        json={"sql": sql}
    )
    job_id = sql_res.json()["id"]

    # Aguardar conclusão
    while True:
        status_res = requests.get(
            f"http://{host}/api/v3/job/{job_id}",
            headers=headers
        )

        if status_res.json().get("jobState") == "COMPLETED":
            break

        time.sleep(1)

    # Buscar todos os resultados com paginação
    all_rows = []
    offset = 0
    limit = 500  # tamanho da página

    while True:
        result_res = requests.get(
            f"http://{host}/api/v3/job/{job_id}/results?offset={offset}&limit={limit}",
            headers=headers
        )
        data = result_res.json()

        # Pegar colunas na primeira iteração
        if offset == 0:
            columns = [col["name"] for col in data["schema"]]

        rows = data["rows"]

        if not rows:  # Se não há mais linhas, sair do loop
            break

        all_rows.extend(rows)
        offset += limit

    return pd.DataFrame(all_rows, columns=columns)
