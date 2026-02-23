from langchain.tools import BaseTool

from src.connectors.dremio import client


class DremioSalesQueryTool(BaseTool):
    name: str = "consultar_vendas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS, faturamento, receita ou dados financeiros. "
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
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            return df.to_string(index=False)
        except Exception as e:
            return f"Erro ao consultar Dremio (vendas): {str(e)}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
