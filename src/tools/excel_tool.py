import asyncio
import base64
import io
import json
import logging
import uuid

import pandas as pd
import redis as redis_lib
from langchain.tools import BaseTool

from src.connectors.dremio import client as dremio_client
from src.connectors.mysql import client as mysql_client
from src.config import REDIS_URL
from src.tools.utils import strip_markdown

logger = logging.getLogger(__name__)

_EXCEL_KEY_PREFIX = "excel:"
_EXCEL_TTL = 120  # seconds

_redis = redis_lib.Redis.from_url(REDIS_URL, decode_responses=True)


class ExcelExportTool(BaseTool):
    name: str = "exportar_excel"
    description: str = (
        "Use SOMENTE quando o usuario pedir EXPLICITAMENTE os dados em Excel, planilha ou .xlsx. "
        "NUNCA use para respostas normais de dados em texto. "
        "Input: JSON com campos: "
        "'sql' (query SQL que retorna os dados desejados — pode ter quantas colunas forem necessarias, "
        "sem limite de colunas como nas outras ferramentas), "
        "'nome_arquivo' (OBRIGATORIO: nome descritivo do arquivo .xlsx com datas concretas — NUNCA use termos vagos como "
        "'ontem', 'hoje', 'semana_passada'. Exemplos: 'vendas_jan_2026.xlsx', 'vendas_03_03_a_09_03_2026.xlsx', "
        "'compras_marco_2026.xlsx'), "
        "'fonte' (OBRIGATORIO: 'dremio' para dados de vendas/faturamento/delivery/metas, "
        "'mysql' para dados de compras/fornecedores). "
        "Use a mesma logica de query SQL que usaria para as outras ferramentas, mas pode retornar "
        "todas as colunas necessarias para uma planilha completa (datas, casas, categorias, valores, etc.). "
        "Exemplo dremio: {\"sql\": \"SELECT CAST(data_evento AS DATE) AS data, casa_ajustado, "
        "SUM(valor_liquido_final) AS total FROM views.\\\"AI_AGENTS\\\".\\\"fSales\\\" "
        "WHERE CAST(data_evento AS DATE) BETWEEN '2026-01-01' AND '2026-01-31' "
        "GROUP BY CAST(data_evento AS DATE), casa_ajustado ORDER BY data, casa_ajustado\", "
        "\"nome_arquivo\": \"vendas_dia_a_dia_jan_2026.xlsx\", \"fonte\": \"dremio\"}. "
        "Exemplo mysql: {\"sql\": \"SELECT `Fantasia`, `D. Lancamento`, `Razao Emitente`, "
        "`Descricao Item`, `V. Total` FROM `tabela_compras` WHERE ...\", "
        "\"nome_arquivo\": \"compras_marco_2026.xlsx\", \"fonte\": \"mysql\"}. "
        "Apos a ferramenta retornar, inclua na Final Answer EXATAMENTE o conteudo retornado "
        "(o marcador [EXCEL:...]) seguido de uma mensagem curta confirmando. "
        "Exemplo: '[EXCEL:excel:abc123|caption:vendas_jan_2026.xlsx]\nPlanilha gerada e enviada!'"
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        try:
            params = json.loads(query)
        except json.JSONDecodeError as e:
            return f"Erro: input deve ser JSON valido. Detalhe: {e}"

        sql          = params.get("sql", "").strip()
        nome_arquivo = params.get("nome_arquivo", "dados.xlsx").strip()
        fonte        = params.get("fonte", "dremio").strip().lower()

        if not sql:
            return "Erro: campo 'sql' e obrigatorio."

        if not nome_arquivo.endswith(".xlsx"):
            nome_arquivo += ".xlsx"

        logger.info("Gerando Excel '%s' fonte=%s", nome_arquivo, fonte)
        try:
            df = mysql_client(sql) if fonte == "mysql" else dremio_client(sql)
        except Exception as e:
            logger.error("Erro ao executar query do Excel: %s", e)
            return f"Erro ao consultar dados para o Excel: {e}"

        if df.empty:
            return "Nenhum dado encontrado para gerar a planilha."

        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Dados")
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
        except Exception as e:
            logger.error("Erro ao gerar arquivo Excel: %s", e)
            return f"Erro ao gerar o arquivo Excel: {e}"

        key = f"{_EXCEL_KEY_PREFIX}{uuid.uuid4().hex}"
        _redis.setex(key, _EXCEL_TTL, b64)
        logger.info("Excel armazenado em Redis: %s (%d rows)", key, len(df))

        return f"[EXCEL:{key}|caption:{nome_arquivo}]"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)
