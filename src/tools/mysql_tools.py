import re
import asyncio
from langchain.tools import BaseTool

from src.connectors.mysql import client
from src.tools.fantasia_abreviacao import ABREVIACAO_TO_FANTASIA

# Hint compacto incluído na description para o agente LLM já gerar o SQL correto
_ABREV_HINT = (
    "Abreviações válidas para `Fantasia` (use SEMPRE o nome fantasia no SQL, nunca a abreviação): "
    + ", ".join(f"{abr}={fan}" for abr, fan in ABREVIACAO_TO_FANTASIA.items())
    + ". "
)


def _strip_markdown(query: str) -> str:
    """Remove blocos de markdown (```sql ... ```) que o agente pode gerar."""
    query = query.strip()
    query = re.sub(r'^```\w*\s*', '', query)
    query = re.sub(r'\s*```$', '', query)
    return query.strip()


def _replace_abbreviations_in_query(query: str) -> str:
    """Substitui abreviações por nomes fantasia dentro de literais SQL (segurança extra)."""
    def _replace(match: re.Match) -> str:
        quote = match.group(1)
        value = match.group(2).strip().upper()
        if value in ABREVIACAO_TO_FANTASIA:
            return quote + ABREVIACAO_TO_FANTASIA[value] + quote
        return match.group(0)

    query = re.sub(r"('([^']*)')", lambda m: _replace(re.match(r"('([^']*)')", m.group(0))), query)
    query = re.sub(r'("([^"]*)")', lambda m: _replace(re.match(r'("([^"]*)")', m.group(0))), query)
    return query


class MySQLPurchasesQueryTool(BaseTool):
    name: str = "consultar_compras"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre COMPRAS, pedidos de compra ou fornecedores. e seja direto nas repostas "
        "Executa SQL no MySQL. Banco: DW_FS_022. Tabela: `505 COMPRA`. "
        "IMPORTANTE: todos os nomes de colunas com espaços ou acentos precisam de backticks. "
        "Colunas disponíveis: "
        "`Fantasia` (TEXT, nome fantasia da empresa o nome da casa (sempre pesquise em maiusculo)), "
        "`D. Lançamento` (DATE, data de lançamento da nota, data oficial da compra), "
        "`N. Nota` (BIGINT, número da nota fiscal), "
        "`Razão Emitente` (TEXT, razão social do fornecedor), "
        "`Item` (TEXT, código do item/produto), "
        "`Descrição Item` (TEXT, nome do produto comprado), "
        "`Grande Grupo` (TEXT, grande grupo do produto, é o grupo principal (ALIMENTOS, BEBIDAS e VINHOS)), "
        "`Grupo` (TEXT, grupo do produto), "
        "`Subgrupo` (TEXT, subgrupo do produto), "
        "`Q. Estoque` (DECIMAL, quantidade convertida em unidade de estoque), "
        "`V. Unitário Convertido` (DECIMAL, valor unitário convertido para UM padrão), "
        "`V. Total` (DECIMAL, valor total da compra, some essa coluna para ter o total de compras). "
        + _ABREV_HINT
        + "Input: query SQL válida para MySQL."
    )

    def _run(self, query: str) -> str:
        query = _strip_markdown(query)
        query = _replace_abbreviations_in_query(query)
        print(f"[MYSQL TOOL] Executando query: {query}", flush=True)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            print(f"[MYSQL TOOL] Query OK — {len(df)} linhas retornadas.", flush=True)
            return df.to_string(index=False)
        except Exception as e:
            print(f"[MYSQL TOOL] ERRO: {type(e).__name__}: {e}", flush=True)
            return f"Erro ao consultar MySQL (compras): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)
