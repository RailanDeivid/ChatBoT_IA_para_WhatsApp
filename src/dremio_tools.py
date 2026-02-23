from langchain.tools import BaseTool

from src.dremio_connector import client


class DremioSalesQueryTool(BaseTool):
    name: str = "consultar_vendas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS, faturamento, receita ou dados financeiros. "
        "Executa SQL no Dremio. Tabela principal: views.\"financial_sales_testes\". "
        "Para descobrir as colunas disponíveis execute: DESCRIBE views.\"financial_sales_testes\". "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            return df.to_string(index=False)
        except Exception as e:
            return f"Erro ao consultar Dremio (vendas): {str(e)}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
