from langchain.tools import BaseTool

from src.mysql_connector import client


class MySQLPurchasesQueryTool(BaseTool):
    name: str = "consultar_compras"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre COMPRAS, pedidos de compra ou fornecedores. "
        "Executa SQL no MySQL. Tabela principal: `505 COMPRA` (use backticks no nome por causa do espaço). "
        "Para descobrir as colunas disponíveis execute: DESCRIBE `505 COMPRA`. "
        "Input: query SQL válida para MySQL."
    )

    def _run(self, query: str) -> str:
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            return df.to_string(index=False)
        except Exception as e:
            return f"Erro ao consultar MySQL (compras): {str(e)}"

    async def _arun(self, query: str) -> str:
        return self._run(query)
