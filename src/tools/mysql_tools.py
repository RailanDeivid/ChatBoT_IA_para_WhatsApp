from langchain.tools import BaseTool

from src.connectors.mysql import client


class MySQLPurchasesQueryTool(BaseTool):
    name: str = "consultar_compras"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre COMPRAS, pedidos de compra ou fornecedores. "
        "Executa SQL no MySQL. Banco: DW_FS_022. Tabela: `505 COMPRA`. "
        "IMPORTANTE: todos os nomes de colunas com espaços ou acentos precisam de backticks. "
        "Colunas disponíveis: "
        "`Fantasia` (TEXT, nome fantasia da empresa), "
        "`D. Lançamento` (DATE, data de lançamento da nota, data oficial da compra), "
        "`N. Nota` (BIGINT, número da nota fiscal), "
        "`Razão Emitente` (TEXT, razão social do fornecedor), "
        "`Item` (TEXT, código do item/produto), "
        "`Descrição Item` (TEXT, nome do produto comprado), "
        "`Grande Grupo` (TEXT, grande grupo do produto), "
        "`Grupo` (TEXT, grupo do produto), "
        "`Subgrupo` (TEXT, subgrupo do produto), "
        "`Q. Estoque` (DECIMAL, quantidade convertida em unidade de estoque), "
        "`V. Unitário Convertido` (DECIMAL, valor unitário convertido para UM padrão), "
        "`V. Total` (DECIMAL, valor total da compra, somre essa coluna para ter o total de compras), "
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
