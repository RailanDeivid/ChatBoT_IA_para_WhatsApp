import pandas as pd
import requests
import time

from src.config import (
    DREMIO_HOST,
    DREMIO_USER,
    DREMIO_PASSWORD
)

# Cache do token para evitar login a cada query
_token_cache: dict = {}


def _get_token(host: str, username: str, password: str) -> str:
    cache_key = f"{host}:{username}"
    cached = _token_cache.get(cache_key)

    if cached:
        # Valida se o token ainda funciona
        test = requests.get(
            f"http://{host}/api/v3/catalog",
            headers={"Authorization": f"_dremio{cached}"},
            timeout=5,
        )
        if test.status_code == 200:
            return cached

    # Login
    login_res = requests.post(
        f"http://{host}/apiv2/login",
        json={"userName": username, "password": password},
        timeout=10,
    )
    login_res.raise_for_status()
    token = login_res.json().get("token")
    _token_cache[cache_key] = token
    return token


def client(sql, host=None, username=None, password=None):
    """
    Executa uma query SQL no Dremio e retorna um DataFrame.

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

    token = _get_token(host, username, password)
    headers = {"Authorization": f"_dremio{token}"}

    # Executar query
    sql_res = requests.post(
        f"http://{host}/api/v3/sql",
        headers=headers,
        json={"sql": sql},
        timeout=30,
    )
    sql_res.raise_for_status()
    job_id = sql_res.json()["id"]

    # Aguardar conclusão (máx 120s)
    for _ in range(120):
        status_res = requests.get(
            f"http://{host}/api/v3/job/{job_id}",
            headers=headers,
            timeout=10,
        )
        job_state = status_res.json().get("jobState")

        if job_state == "COMPLETED":
            break
        if job_state in ("FAILED", "CANCELED"):
            error = status_res.json().get("errorMessage", "Erro desconhecido")
            raise RuntimeError(f"Job Dremio falhou ({job_state}): {error}")

        time.sleep(1)
    else:
        raise TimeoutError("Timeout aguardando job Dremio (120s)")

    # Buscar resultados com paginação
    all_rows = []
    columns = []
    offset = 0
    limit = 500

    while True:
        result_res = requests.get(
            f"http://{host}/api/v3/job/{job_id}/results?offset={offset}&limit={limit}",
            headers=headers,
            timeout=30,
        )
        data = result_res.json()

        if offset == 0:
            columns = [col["name"] for col in data["schema"]]

        rows = data["rows"]
        if not rows:
            break

        all_rows.extend(rows)
        offset += limit

    return pd.DataFrame(all_rows, columns=columns)
