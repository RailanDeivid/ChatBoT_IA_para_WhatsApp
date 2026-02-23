import time
import pandas as pd
import requests

from src.config import DREMIO_HOST, DREMIO_USER, DREMIO_PASSWORD


_token_cache: dict[str, tuple[str, float]] = {}  # key -> (token, timestamp)
_TOKEN_TTL = 3600  # tokens Dremio duram ~1h; renova por tempo sem chamada extra


def _get_token(host: str, username: str, password: str) -> str:
    cache_key = f"{host}:{username}"
    cached = _token_cache.get(cache_key)

    if cached:
        token, created_at = cached
        if time.time() - created_at < _TOKEN_TTL:
            return token

    login_res = requests.post(
        f"http://{host}/apiv2/login",
        json={"userName": username, "password": password},
        timeout=10,
    )
    login_res.raise_for_status()
    token = login_res.json()["token"]
    _token_cache[cache_key] = (token, time.time())
    return token


def client(sql: str) -> pd.DataFrame:
    """Executa query SQL no Dremio e retorna DataFrame."""
    print("[DREMIO] Obtendo token...", flush=True)
    token = _get_token(DREMIO_HOST, DREMIO_USER, DREMIO_PASSWORD)
    headers = {"Authorization": f"_dremio{token}"}
    base = f"http://{DREMIO_HOST}"

    # Submete a query
    print("[DREMIO] Submetendo query ao servidor...", flush=True)
    sql_res = requests.post(
        f"{base}/api/v3/sql",
        headers=headers,
        json={"sql": sql},
        timeout=30,
    )
    sql_res.raise_for_status()
    job_id = sql_res.json()["id"]
    print(f"[DREMIO] Job criado: {job_id}. Aguardando conclusão...", flush=True)

    # Aguarda conclusão — polling a cada 3s, timeout generoso, retry em ConnectTimeout
    t_start = time.time()
    last_state = None
    max_wait = 180  # segundos máximos de espera
    poll_interval = 3  # intervalo entre checks (menos pressão no servidor)

    while time.time() - t_start < max_wait:
        try:
            status_res = requests.get(
                f"{base}/api/v3/job/{job_id}", headers=headers, timeout=30
            )
            job_state = status_res.json().get("jobState")
        except requests.exceptions.ConnectTimeout:
            elapsed = int(time.time() - t_start)
            print(f"[DREMIO] Timeout ao checar status ({elapsed}s) — tentando novamente...", flush=True)
            time.sleep(poll_interval)
            continue

        if job_state != last_state:
            print(f"[DREMIO] Estado do job: {job_state} ({int(time.time() - t_start)}s)", flush=True)
            last_state = job_state

        if job_state == "COMPLETED":
            break
        if job_state in ("FAILED", "CANCELED"):
            error = status_res.json().get("errorMessage", "Erro desconhecido")
            raise RuntimeError(f"Job Dremio falhou ({job_state}): {error}")

        time.sleep(poll_interval)
    else:
        raise TimeoutError(f"Timeout aguardando job Dremio ({max_wait}s)")

    # Busca resultados com paginação — limite de 20 páginas (10.000 linhas)
    all_rows: list = []
    columns: list = []
    offset = 0
    limit = 500
    MAX_PAGES = 20

    for page in range(MAX_PAGES):
        result_res = requests.get(
            f"{base}/api/v3/job/{job_id}/results?offset={offset}&limit={limit}",
            headers=headers,
            timeout=30,
        )
        data = result_res.json()

        if page == 0:
            columns = [col["name"] for col in data["schema"]]

        rows = data.get("rows", [])
        if not rows:
            break

        all_rows.extend(rows)
        offset += limit

    return pd.DataFrame(all_rows, columns=columns)
