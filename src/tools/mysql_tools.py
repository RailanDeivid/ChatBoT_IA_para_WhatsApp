import asyncio
import logging
import re

from langchain.tools import BaseTool

from src.connectors.mysql import client
from src.tools.fantasia_abreviacao import ABREVIACAO_TO_FANTASIA
from src.tools.utils import strip_markdown

logger = logging.getLogger(__name__)

# Hint compacto incluído na description para o agente LLM já gerar o SQL correto
_ABREV_HINT = (
    "Abreviações válidas para `Fantasia` (use SEMPRE o nome fantasia no SQL, nunca a abreviação): "
    + ", ".join(f"{abr}={fan}" for abr, fan in ABREVIACAO_TO_FANTASIA.items())
    + ". "
)


def _replace_abbreviations_in_query(query: str) -> str:
    """Substitui abreviações por nomes fantasia dentro de literais SQL (segurança extra)."""
    def _replace(match: re.Match) -> str:
        quote = match.group(1)
        value = match.group(2).strip().upper()
        return quote + ABREVIACAO_TO_FANTASIA.get(value, value) + quote

    query = re.sub(r"(['])([^']*)\1", _replace, query)
    query = re.sub(r'(["])([^"]*)\1', _replace, query)
    return query


class MySQLPurchasesQueryTool(BaseTool):
    name: str = "consultar_compras"
    description: str = (
        "QUANDO USAR: OBRIGATORIO chamar esta ferramenta para QUALQUER pergunta sobre COMPRAS, "
        "pedidos de compra, fornecedores ou notas fiscais de entrada. "
        "PALAVRAS-CHAVE que ativam esta ferramenta: compra, compras, comprou, fornecedor, fornecedores, "
        "nota fiscal, NF, pedido de compra, quanto foi comprado, total comprado, custo, "
        "insumo, ingrediente, produto comprado, valor de compra, compra de alimentos, compra de bebidas. "
        "NUNCA responda com dados de compras sem antes chamar esta ferramenta. "
        "NUNCA invente valores — use SOMENTE os dados retornados pela ferramenta. "
        "Executa SQL no MySQL. Banco: DW_FS_022. Tabela: `505 COMPRA`. "
        "IMPORTANTE: TODOS os nomes de colunas com espacos ou acentos precisam de backticks. "
        "SEMPRE agrupe as queries para trazer resultado limpo e direto. "
        "Colunas disponíveis: "
        "`Fantasia` (TEXT, nome fantasia da casa — SEMPRE pesquise em MAIUSCULO), "
        "`D. Lançamento` (DATE, data oficial da compra/nota), "
        "`N. Nota` (BIGINT, numero da nota fiscal), "
        "`Razão Emitente` (TEXT, razao social do fornecedor), "
        "`Item` (TEXT, codigo do item/produto), "
        "`Descrição Item` (TEXT, nome do produto comprado), "
        "`Grande Grupo` (TEXT, grupo principal: ALIMENTOS, BEBIDAS, VINHOS — use para agrupar por categoria ampla), "
        "`Grupo` (TEXT, subgrupo do produto — use para detalhar por tipo de produto), "
        "`Q. Estoque` (DECIMAL, quantidade em unidade de estoque), "
        "`V. Unitário Convertido` (DECIMAL, valor unitario convertido), "
        "`V. Total` (DECIMAL, valor total da compra — use SUM(`V. Total`) para totalizar). "
        + _ABREV_HINT
        + "Input: query SQL valida para MySQL."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        query = _replace_abbreviations_in_query(query)
        logger.info("Executando query MySQL: %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return df.to_string(index=False)
        except Exception as e:
            logger.error("ERRO MySQL: %s: %s", type(e).__name__, e)
            return f"Erro ao consultar MySQL (compras): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)
