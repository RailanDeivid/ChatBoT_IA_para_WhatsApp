from langchain.tools import BaseTool

from src.mysql_connector import client


class MySQLPurchasesQueryTool(BaseTool):
    name: str = "consultar_compras"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre COMPRAS, pedidos de compra ou fornecedores. "
        "Executa SQL no MySQL. Banco: DW_FS_022. Tabela: `505 COMPRA`. "
        "IMPORTANTE: todos os nomes de colunas com espaços ou acentos precisam de backticks. "
        "Colunas disponíveis: "
        "`Empresa` (INT, código da empresa), "
        "`Fantasia` (TEXT, nome fantasia da empresa), "
        "`D. Emissão` (DATE, data de emissão da nota de compra), "
        "`D. Lançamento` (DATE, data de lançamento da nota), "
        "`N. Nota` (BIGINT, número da nota fiscal), "
        "`Série` (TEXT, série da nota fiscal), "
        "`Natureza Fiscal` (TEXT, natureza da operação fiscal), "
        "`Razão Emitente` (TEXT, razão social do fornecedor), "
        "`cpf_cnpj_emitente` (TEXT, CPF/CNPJ do fornecedor), "
        "`nm_cidade_emissao` (TEXT, cidade do fornecedor), "
        "`UF Emissão` (TEXT, estado UF do fornecedor), "
        "`Razão Destinatário` (TEXT, razão social do destinatário), "
        "`Item` (TEXT, código do item/produto), "
        "`Descrição Item` (TEXT, nome do produto comprado), "
        "`Família` (TEXT, família do produto), "
        "`Grande Grupo` (TEXT, grande grupo do produto), "
        "`Grupo` (TEXT, grupo do produto), "
        "`Subgrupo` (TEXT, subgrupo do produto), "
        "`Embalagem` (TEXT, tipo de embalagem), "
        "`UM` (TEXT, unidade de medida), "
        "`Q. Embalagens` (DECIMAL, quantidade de embalagens compradas), "
        "`Q. Estoque` (DECIMAL, quantidade convertida em unidade de estoque), "
        "`V. Embalagem` (DECIMAL, valor por embalagem), "
        "`V. Unitário Convertido` (DECIMAL, valor unitário convertido para UM padrão), "
        "`V. Desconto` (DECIMAL, valor de desconto concedido), "
        "`V. Total` (DECIMAL, valor total da compra), "
        "`V. Custo Médio` (DECIMAL, custo médio do produto), "
        "`CFOP` (INT, código fiscal da operação), "
        "`Descrição CFOP` (TEXT, descrição da operação fiscal), "
        "`C. Gerencial` (INT, código do centro gerencial), "
        "`Descrição C. Gerencial` (TEXT, descrição do centro gerencial), "
        "`ds_centro_custo` (TEXT, descrição do centro de custo), "
        "`Origem` (TEXT, origem do registro). "
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
