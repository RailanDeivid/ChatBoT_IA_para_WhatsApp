import re
import asyncio
from langchain.tools import BaseTool

from src.connectors.dremio import client


def _strip_markdown(query: str) -> str:
    """Remove blocos de markdown (```sql ... ```) que o agente pode gerar."""
    query = query.strip()
    query = re.sub(r'^```\w*\s*', '', query)
    query = re.sub(r'\s*```$', '', query)
    return query.strip()


class DremioSalesQueryTool(BaseTool):
    name: str = "consultar_vendas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS, faturamento, receita ou dados financeiros. Sempre agrupar as querys para tarzer um resultado mais limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"financial_sales_testes\". "
        "Colunas disponíveis: "
        "codigo_casa (TEXT, código do estabelecimento é o nome da CASA), "
        "data_evento (DATE, data da venda), "
        "descricao_produto (TEXT, nome do produto vendido), "
        "quantidade (FLOAT, quantidade vendida), "
        "valor_produto (DOUBLE, valor unitário do produto), "
        "nome_funcionario (TEXT, nome do funcionário), "
        "valor_liquido_final (DOUBLE, valor líquido final após descontos é o valor a ser considerado), "
        "distribuicao_pessoas (FLOAT, distribuição por pessoas, somar a coluna para ter o Fluxo). "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = _strip_markdown(query)
        print(f"[DREMIO TOOL] Executando query: {query}", flush=True)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            print(f"[DREMIO TOOL] Query OK — {len(df)} linhas retornadas.", flush=True)
            return df.to_string(index=False)
        except Exception as e:
            print(f"[DREMIO TOOL] ERRO: {type(e).__name__}: {e}", flush=True)
            return f"Erro ao consultar Dremio (vendas): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)
