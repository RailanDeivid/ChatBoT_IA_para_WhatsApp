from langchain.tools import BaseTool

from src.connectors.dremio import client


class DremioSalesQueryTool(BaseTool):
    name: str = "consultar_vendas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS, faturamento, receita ou dados financeiros. "
        "Executa SQL no Dremio. Tabela: views.\"financial_sales_testes\". "
        "Colunas disponíveis: "
        "codigo_casa (TEXT, código do estabelecimento), "
        "terminal (TEXT, terminal de venda), "
        "data_evento (DATE, data da venda), "
        "descricao_produto_grupo_pai (TEXT, grupo pai do produto), "
        "descricao_grupo_inicial (TEXT, grupo inicial do produto), "
        "descricao_produto_grupo (TEXT, grupo do produto), "
        "hora_item (BIGINT, hora do item), "
        "descricao_produto (TEXT, nome do produto vendido), "
        "quantidade (FLOAT, quantidade vendida), "
        "valor_produto (DOUBLE, valor unitário do produto), "
        "valor_venda (DOUBLE, valor total da venda), "
        "desconto_total (DOUBLE, desconto aplicado), "
        "nome_funcionario (TEXT, nome do funcionário), "
        "codigo_funcionario (TEXT, código do funcionário), "
        "valor_venda_s_pendura (DOUBLE, valor de venda sem pendura), "
        "valor_liquido_final (DOUBLE, valor líquido final após descontos), "
        "distribuicao_pessoas (FLOAT, distribuição por pessoas). "
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
