import asyncio
import logging

from langchain.tools import BaseTool

from src.connectors.dremio import client
from src.tools.fantasia_abreviacao import ABREVIACAO_TO_FANTASIA
from src.tools.utils import strip_markdown, format_df

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
        "Executa SQL no Dremio. Tabela: views.\"AI_AGENTS\".\"fSales\". "
        "Se for perguntado sobre ticket medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas))."
        "Colunas disponíveis: "
        "casa_ajustado (TEXT, código do estabelecimento é o nome da CASA), "
        "alavanca (TEXT, vertical/segmento do estabelecimento. Use para agrupar ou filtrar vendas por alavanca (tambem chamada de vertical). Valores: Bar, Restaurante, iraja), "
        "data_evento (DATE, data da venda), "
        "hora_item (FLOAT, hora do item. Use para agrupar por horário. OBRIGATÓRIO: sempre ordene usando ORDER BY CASE WHEN hora_item < 6 THEN hora_item + 24 ELSE hora_item END para que a sequência comece em 06:00 e termine em 05:00 do dia seguinte), "
        "descricao_produto (TEXT, nome do produto vendido), "
        "quantidade (FLOAT, quantidade vendida), "
        "valor_produto (DOUBLE, valor unitário do produto), "
        "nome_funcionario (TEXT, nome do funcionário), "
        "valor_liquido_final (DOUBLE, valor líquido final após descontos é o valor a ser considerado), "
        "desconto_total (FLOAT, desconto total aplicado, use para calcular o valor total de descontos), "
        "distribuicao_pessoas (FLOAT, distribuição por pessoas, somar a coluna para ter o Fluxo), "
        "ticket_medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas)), "
        "Grande_Grupo (TEXT, categoria principal do produto. Use para filtrar ou agrupar por categoria ampla. Valores: ALIMENTOS, BEBIDAS, VINHOS, OUTRAS COMPRAS. Use quando o usuario perguntar sobre vendas por categoria, vendas de alimentos, bebidas, vinhos ou outras compras), "
        "Grupo (TEXT, subcategoria do produto dentro do Grande_Grupo. Exemplos: SUCOS, CERVEJAS, CHOPS, DRINKS, COQUETEIS, AGUAS, etc. Use quando o usuario perguntar sobre vendas de um tipo específico de bebida ou produto como chop, cerveja, drink, suco), "
        "Sub_Grupo (TEXT, segmentação mais detalhada do produto. Exemplos: ALCOOLICAS, NAO ALCOOLICAS, PRODUTOS DE EVENTO, VENDAS DE ALIMENTOS, etc. Use quando o usuario perguntar sobre vendas de alcoholicos, nao alcoholicos, eventos ou segmentacoes similares). "
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
            return format_df(df)
        except Exception as e:
            logger.error("ERRO Dremio: %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (vendas): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)


class DremioDeliveryQueryTool(BaseTool):
    name: str = "consultar_delivery"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre VENDAS DELIVERY, pedidos delivery, faturamento delivery. Sempre agrupar as querys para trazer um resultado mais limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"AI_AGENTS\".\"fSalesDelivery\". "
        "Se for perguntado sobre ticket medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas))."
        "Colunas disponíveis: "
        "casa_ajustado (TEXT, código do estabelecimento é o nome da CASA), "
        "alavanca (TEXT, vertical/segmento do estabelecimento. Use para agrupar ou filtrar vendas por alavanca (tambem chamada de vertical). Valores: Bar, Restaurante, iraja), "
        "data_evento (DATE, data do pedido delivery), "
        "hora_item (FLOAT, hora do item. Use para agrupar por horário. OBRIGATÓRIO: sempre ordene usando ORDER BY CASE WHEN hora_item < 6 THEN hora_item + 24 ELSE hora_item END para que a sequência comece em 06:00 e termine em 05:00 do dia seguinte), "
        "codigo_produto (TEXT, código do produto), "
        "descricao_produto (TEXT, nome do produto vendido), "
        "quantidade (FLOAT, quantidade de itens vendidos), "
        "valor_produto (DOUBLE, valor unitário do produto), "
        "valor_venda (DOUBLE, valor de venda antes de descontos), "
        "desconto_produto (FLOAT, desconto aplicado no produto), "
        "desconto_total (FLOAT, desconto total aplicado no pedido), "
        "nome_funcionario (TEXT, canal/plataforma do pedido delivery — ex: IFOOD, RAPPI, APP PROPRIO, TERMINAL. Use esta coluna para agrupar por plataforma, app ou canal de venda), "
        "valor_conta (DOUBLE, valor total da conta/pedido), "
        "valor_liquido_final (DOUBLE, valor líquido final após descontos — use para totais de faturamento), "
        "distribuicao_pessoas (FLOAT, distribuição por pessoas, somar a coluna para ter o Fluxo), "
        "ticket_medio (não é coluna — calcular como SUM(valor_liquido_final) / SUM(distribuicao_pessoas)), "
        "Grande_Grupo (TEXT, categoria principal do produto. Use para filtrar ou agrupar por categoria ampla. Valores: ALIMENTOS, BEBIDAS, VINHOS, OUTRAS COMPRAS. Use quando o usuario perguntar sobre delivery de alimentos, bebidas, vinhos ou outras compras por categoria), "
        "Grupo (TEXT, subcategoria do produto dentro do Grande_Grupo. Exemplos: SUCOS, CERVEJAS, CHOPS, DRINKS, COQUETEIS, AGUAS, etc. Use quando o usuario perguntar sobre delivery de um tipo específico como chop, cerveja, drink, suco), "
        "Sub_Grupo (TEXT, segmentação mais detalhada do produto. Exemplos: ALCOOLICAS, NAO ALCOOLICAS, PRODUTOS DE EVENTO, VENDAS DE ALIMENTOS, etc. Use quando o usuario perguntar sobre delivery de alcoólicos, nao alcoólicos, eventos ou segmentacoes similares). "
        + _CODIGO_CASA_HINT
        + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
        "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        logger.info("Executando query Dremio (delivery): %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return format_df(df)
        except Exception as e:
            logger.error("ERRO Dremio (delivery): %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (delivery): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)


class DremioEstornosQueryTool(BaseTool):
    name: str = "consultar_estornos"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre ESTORNOS, cancelamentos ou devoluções de produtos. "
        "Sempre agrupar as querys para trazer um resultado mais limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"AI_AGENTS\".\"fEstornos\". "
        "Colunas disponíveis: "
        "casa_ajustado (TEXT, código do estabelecimento é o nome da CASA), "
        "alavanca (TEXT, vertical/segmento do estabelecimento. Valores: Bar, Restaurante, iraja), "
        "data_evento (TIMESTAMP, data e hora do estorno — use CAST(data_evento AS DATE) para filtrar por data), "
        "codigo_produto (INT, código do produto estornado), "
        "descricao_produto (TEXT, nome do produto estornado), "
        "quantidade (FLOAT, quantidade estornada), "
        "valor_produto (DOUBLE, valor total do estorno — USE SUM(valor_produto) para totalizar), "
        "descricao_motivo_estorno (TEXT, motivo do estorno — USE para agrupar e contar total de estornos por motivo: GROUP BY descricao_motivo_estorno), "
        "perda (INT, indica se houve perda: 1 = sim, 0 = não), "
        "tipo_estorno (TEXT, tipo do estorno — ex: COM FATURAMENTO), "
        "nome_cliente (TEXT, identificação do cliente), "
        "nome_funcionario (TEXT, nome do funcionário que realizou o estorno), "
        "nome_usuario_funcionario (TEXT, login do funcionário), "
        "Grande_Grupo (TEXT, categoria principal do produto estornado. Use para filtrar ou agrupar por categoria ampla. Valores: ALIMENTOS, BEBIDAS, VINHOS, OUTRAS COMPRAS. Use quando o usuario perguntar sobre estornos de alimentos, bebidas, vinhos ou outras compras por categoria), "
        "Grupo (TEXT, subcategoria do produto estornado dentro do Grande_Grupo. Exemplos: SUCOS, CERVEJAS, CHOPS, DRINKS, COQUETEIS, AGUAS, etc. Use quando o usuario perguntar sobre estornos de um tipo específico como chop, cerveja, drink, suco), "
        "Sub_Grupo (TEXT, segmentação mais detalhada do produto estornado. Exemplos: ALCOOLICAS, NAO ALCOOLICAS, PRODUTOS DE EVENTO, VENDAS DE ALIMENTOS, etc. Use quando o usuario perguntar sobre estornos de alcoólicos, nao alcoólicos, eventos ou segmentacoes similares). "
        + _CODIGO_CASA_HINT
        + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
        "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        logger.info("Executando query Dremio (estornos): %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return format_df(df)
        except Exception as e:
            logger.error("ERRO Dremio (estornos): %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (estornos): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)


class DremioMetasQueryTool(BaseTool):
    name: str = "consultar_metas"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre METAS, ORÇAMENTO, BUDGET, RECEITA META, FLUXO META, "
        "atingimento de meta, vendas vs meta, faturamento vs orçamento, fluxo vs meta. "
        "Sempre agrupe as queries para trazer resultado limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"AI_AGENTS\".\"dMetas_Casas\". "
        "ATENCAO: colunas com espaco devem ser sempre entre aspas duplas no SQL. "
        "Colunas disponíveis: "
        "DATA (TIMESTAMP, data da meta — use CAST(DATA AS DATE) para filtrar por data), "
        "\"RECEITA META\" (FLOAT, meta diaria de faturamento/receita — use SUM(\"RECEITA META\") para totalizar), "
        "\"META FLUXO\" (FLOAT, meta diaria de fluxo de pessoas — use SUM(\"META FLUXO\") para totalizar), "
        "casa_ajustado (TEXT, nome completo do estabelecimento. IMPORTANTE: nesta tabela casa_ajustado contem o nome COMPLETO da casa, diferente da tabela de vendas que usa abreviacao. Use este campo para filtrar ou agrupar por casa), "
        "alavanca (TEXT, vertical/segmento. Valores: Bar, Restaurante, Iraja — use para filtrar ou agrupar por alavanca/vertical/BU). "
        "COMO USAR PARA 'VENDAS VS META' OU 'FATURAMENTO VS META': use uma CTE juntando fSales e dMetas_Casas. "
        "Exemplo de padrao CTE para vs meta por casa: "
        "WITH vendas AS (SELECT casa_ajustado, SUM(valor_liquido_final) AS realizado FROM views.\"AI_AGENTS\".\"fSales\" WHERE CAST(data_evento AS DATE) BETWEEN 'AAAA-MM-DD' AND 'AAAA-MM-DD' GROUP BY casa_ajustado), "
        "metas AS (SELECT casa_ajustado, SUM(\"RECEITA META\") AS meta FROM views.\"AI_AGENTS\".\"dMetas_Casas\" WHERE CAST(DATA AS DATE) BETWEEN 'AAAA-MM-DD' AND 'AAAA-MM-DD' GROUP BY casa_ajustado) "
        "SELECT v.casa_ajustado, v.realizado, m.meta, ROUND(v.realizado / m.meta * 100, 2) AS atingimento_pct FROM vendas v JOIN metas m ON v.casa_ajustado = m.casa_ajustado ORDER BY atingimento_pct DESC. "
        "Para fluxo vs meta: substitua valor_liquido_final por SUM(distribuicao_pessoas) e \"RECEITA META\" por \"META FLUXO\". "
        "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
        "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        logger.info("Executando query Dremio (metas): %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return format_df(df)
        except Exception as e:
            logger.error("ERRO Dremio (metas): %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (metas): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)


class DremioPaymentQueryTool(BaseTool):
    name: str = "consultar_formas_pagamento"
    description: str = (
        "Use EXCLUSIVAMENTE para perguntas sobre FORMAS DE PAGAMENTO, mix de pagamentos, "
        "participação de cada forma (dinheiro, cartão, pix, etc), faturamento por forma de pagamento. "
        "Sempre agrupar as querys para trazer um resultado mais limpo e direto. "
        "Executa SQL no Dremio. Tabela: views.\"AI_AGENTS\".\"fFormasPagamento\". "
        "Colunas disponíveis: "
        "cnpj_casa (TEXT, CNPJ do estabelecimento), "
        "casa_ajustado (TEXT, código do estabelecimento é o nome da CASA), "
        "alavanca (TEXT, vertical/segmento do estabelecimento. Use para agrupar ou filtrar vendas por alavanca (tambem chamada de vertical). Valores: Bar, Restaurante, iraja), "
        "data (DATE, data do registro), "
        "descricao_forma_pagamento (TEXT, nome da forma de pagamento — ex: VISA_CREDITO, DINHEIRO, PIX, etc), "
        "pessoas (FLOAT, número de pessoas), "
        "vl_recebido (DOUBLE, valor bruto recebido nessa forma de pagamento — use para totais), "
        + _CODIGO_CASA_HINT
        + "SINTAXE DE DATAS no Dremio: use DATE_SUB(CURRENT_DATE, 1) (ontem), "
        "CURRENT_DATE - INTERVAL '7' DAY (últimos 7 dias), "
        "DATE_TRUNC('month', CURRENT_DATE) (início do mês). "
        "NUNCA use CURRENT_DATE - INTERVAL '1 day' nem CURRENT_DATE - 1. "
        "OBRIGATÓRIO: SEMPRE gere SQL com sintaxe 100% válida para Dremio. "
        "Input: query SQL válida para Dremio."
    )

    def _run(self, query: str) -> str:
        query = strip_markdown(query)
        logger.info("Executando query Dremio (pagamentos): %s", query)
        try:
            df = client(query)
            if df.empty:
                return "Nenhum resultado encontrado."
            logger.info("Query OK — %d linhas retornadas.", len(df))
            return format_df(df)
        except Exception as e:
            logger.error("ERRO Dremio (pagamentos): %s: %s", type(e).__name__, e)
            return f"Erro ao consultar Dremio (pagamentos): {str(e)}"

    async def _arun(self, query: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run, query)
