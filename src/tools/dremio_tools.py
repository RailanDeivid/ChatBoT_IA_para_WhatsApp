import re
import asyncio
from langchain.tools import BaseTool

from src.connectors.dremio import client
from src.tools.fantasia_abreviacao import ABREVIACAO_TO_FANTASIA

# Hint para o agente usar o código abreviado exato no campo codigo_casa
_CODIGO_CASA_HINT = (
    "IMPORTANTE: o campo `codigo_casa` armazena os códigos abreviados das casas DIRETAMENTE. "
    "Use SEMPRE o código abreviado no SQL, NUNCA expanda para o nome completo. "
    "Exemplos de códigos válidos: "
    + ", ".join(ABREVIACAO_TO_FANTASIA.keys())
    + ". "
)


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
        + _CODIGO_CASA_HINT
        + "SINTAXE DE DATAS no Dremio: use CURRENT_DATE - INTERVAL '1' DAY (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
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
