import requests
import pandas as pd
import time
import os
from dotenv import load_dotenv

load_dotenv()

DREMIO_HOST = os.getenv("DREMIO_HOST")
DREMIO_USER = os.getenv("DREMIO_USER")
DREMIO_PASSWORD = os.getenv("DREMIO_PASSWORD")

class DremioClient:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.token = None
        self.headers = None
        self.login()

    def login(self):
        url_login = f"http://{self.host}/apiv2/login"
        payload = {"userName": self.username, "password": self.password}
        res = requests.post(url_login, json=payload)
        self.token = res.json().get("token")
        self.headers = {"Authorization": f"_dremio{self.token}"}

    def execute_query(self, sql):
        res = requests.post(f"http://{self.host}/api/v3/sql", headers=self.headers, json={"sql": sql})
        job_id = res.json()["id"]
        return self._get_results(job_id)

    def _get_results(self, job_id):
        while True:
            status_res = requests.get(f"http://{self.host}/api/v3/job/{job_id}", headers=self.headers)
            if status_res.json().get("jobState") == "COMPLETED":
                result_res = requests.get(f"http://{self.host}/api/v3/job/{job_id}/results", headers=self.headers)
                data = result_res.json()
                columns = [col["name"] for col in data["schema"]]
                rows = data["rows"]
                return pd.DataFrame(rows, columns=columns)
            time.sleep(1)

client = DremioClient(
            host=DREMIO_HOST, 
            username=DREMIO_USER, 
            password=DREMIO_PASSWORD
        )

df = client.execute_query("""SELECT 
codigo_casa, 
cast(data_evento as date) AS DATA, 
--descricao_produto, 
sum(valor_liquido) as gorjeta_geral,
sum(valor_liquido*0.025) as tx_cartao,
sum(valor_liquido*0.33) as retencao_33,
sum(valor_liquido-((valor_liquido*0.025)+(valor_liquido*0.33))) as Saldo_33_cartão,
sum((valor_liquido-((valor_liquido*0.025)+(valor_liquido*0.33)))*0.11) as areas_apoio,
(Saldo_33_cartão-areas_apoio) as valor
FROM datalake.ouro."fat_vendas"
where cast(data_evento as date) BETWEEN '2025-10-30' AND '2025-11-12' and codigo_casa = 'TBB'and
(ilike(descricao_produto,'%gorjeta%') or ilike(descricao_produto,'%repique%'))
GROUP BY 1,2""")
print(df.shape)
