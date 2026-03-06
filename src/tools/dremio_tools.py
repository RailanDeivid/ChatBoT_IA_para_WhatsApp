import asyncio
import logging

from langchain.tools import BaseTool

from src.connectors.dremio import client
from src.tools.fantasia_abreviacao import ABREVIACAO_TO_FANTASIA
from src.tools.utils import strip_markdown

logger = logging.getLogger(__name__)

# Hint para o agente usar o código abreviado exato no campo codigo_casa
_CODIGO_CASA_HINT = (
    "IMPORTANTE: o campo `codigo_casa` armazena os códigos abreviados das casas DIRETAMENTE. "
    "Use SEMPRE o código abreviado no SQL, NUNCA expanda para o nome completo. "
    "Exemplos de códigos válidos: "
    + ", ".join(ABREVIACAO_TO_FANTASIA.keys())
    + ". "
)


class DremioSalesQueryTool(BaseTool):
    name: str = "consultar_vendas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS, faturamento, receita ou dados financeiros. Sempre agrupar as querys para tarzer um resultado mais limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"financial_sales_testes\". "
        "Se for perguntado sobre ticket medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas))."
        "Colunas disponíveis: "
        "codigo_casa (TEXT, código do estabelecimento é o nome da CASA), "
        "data_evento (DATE, data da venda), "
        "descricao_produto (TEXT, nome do produto vendido), "
        "quantidade (FLOAT, quantidade vendida), "
        "valor_produto (DOUBLE, valor unitário do produto), "
        "nome_funcionario (TEXT, nome do funcionário), "
        "valor_liquido_final (DOUBLE, valor líquido final após descontos é o valor a ser considerado), "
        "distribuicao_pessoas (FLOAT, distribuição por pessoas, somar a coluna para ter o Fluxo), "
        "ticket_medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas)). "
        + _CODIGO_CASA_HINT
        + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
        "Para data especifica, use CAST(data_evento AS DATE). "
        "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
        "NÃO use sintaxe de PostgreSQL, MySQL ou outros bancos. "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        logger.info("Executando query Dremio: %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return df.to_string(index=False)
        except Exception as e:
            logger.error("ERRO Dremio: %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (vendas): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)


# class DremioDeliveryQueryTool(BaseTool):
#     name: str = "consultar_delivery"
#     description: str = (
#         "Use EXCLUSIVAMENTE para perguntas sobre VENDAS DELIVERY, pedidos delivery, faturamento delivery. "
#         "Executa SQL no Dremio. Tabela: views.\"fSales_Delivery\". "
#         "Colunas disponíveis: "
#         "codigo_casa (TEXT, código do estabelecimento), "
#         "data_evento (DATE, data do pedido), "
#         "valor_liquido_final (DOUBLE, valor líquido final — use para totais de faturamento), "
#         "quantidade (FLOAT, quantidade de itens). "
#         + _CODIGO_CASA_HINT
#         + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
#         "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
#         "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
#         "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
#         "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
#         "Input: query SQL válida para Dremio."
#     )

#     def _run(self, query: str) -> str:
#         query = strip_markdown(query)
#         logger.info("Executando query Dremio (delivery): %s", query)
#         try:
#             df = client(query)
#             if df.empty:
#                 return "Nenhum resultado encontrado."
#             logger.info("Query OK — %d linhas retornadas.", len(df))
#             return df.to_string(index=False)
#         except Exception as e:
#             logger.error("ERRO Dremio (delivery): %s: %s", type(e).__name__, e)
#             return f"Erro ao consultar Dremio (delivery): {str(e)}"

#     async def _arun(self, query: str) -> str:
#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._run, query)




# class DremioPaymentQueryTool(BaseTool):
#     name: str = "consultar_forma_pagamento"
#     description: str = (
#         "Use EXCLUSIVAMENTE para perguntas sobre faturamento por FORMA DE PAGAMENTO, "
#         "mix de pagamentos, participação de cada forma (dinheiro, cartão, pix, etc). "
#         "Executa SQL no Dremio. Tabela: views.\"tabela_forma_pagamento\". "
#         "Colunas disponíveis: "
#         "codigo_casa (TEXT, código do estabelecimento), "
#         "data_evento (DATE, data da venda), "
#         "forma_pagamento (TEXT, ex: DINHEIRO, CARTAO_CREDITO, PIX), "
#         "valor_total (DOUBLE, valor faturado nessa forma de pagamento). "
#         + _CODIGO_CASA_HINT
#         + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) para ontem, "
#         "DATE_TRUNC('month', CURRENT_DATE) para início do mês. "
#         "Input: query SQL válida para Dremio."
#     )

#     def _run(self, query: str) -> str:
#         query = strip_markdown(query)
#         logger.info("Executando query Dremio (pagamentos): %s", query)
#         try:
#             df = client(query)
#             if df.empty:
#                 return "Nenhum resultado encontrado."
#             logger.info("Query OK — %d linhas retornadas.", len(df))
#             return df.to_string(index=False)
#         except Exception as e:
#             logger.error("ERRO Dremio (pagamentos): %s: %s", type(e).__name__, e)
#             return f"Erro ao consultar Dremio (pagamentos): {str(e)}"

#     async def _arun(self, query: str) -> str:
#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._run, query)
