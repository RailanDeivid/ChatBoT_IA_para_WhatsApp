import pytest
import pandas as pd

from src.tools.utils import strip_markdown, extract_json, _is_pct_col, format_df


class TestStripMarkdown:
    def test_remove_bloco_sql(self):
        assert strip_markdown("```sql\nSELECT 1\n```") == "SELECT 1"

    def test_remove_bloco_sem_linguagem(self):
        assert strip_markdown("```\nSELECT 1\n```") == "SELECT 1"

    def test_sem_markdown_nao_muda(self):
        assert strip_markdown("SELECT 1") == "SELECT 1"

    def test_extrai_sql_de_json(self):
        result = strip_markdown('{"sql": "SELECT 1"}')
        assert result == "SELECT 1"

    def test_extrai_query_de_json(self):
        result = strip_markdown('{"query": "SELECT 2"}')
        assert result == "SELECT 2"

    def test_json_invalido_retorna_original(self):
        result = strip_markdown('{"invalido json')
        assert "invalido" in result

    def test_strip_espacos(self):
        assert strip_markdown("  SELECT 1  ") == "SELECT 1"


class TestExtractJson:
    def test_json_simples(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_json_com_markdown(self):
        assert extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}

    def test_trailing_comma(self):
        assert extract_json('{"a": 1,}') == {"a": 1}

    def test_aspas_simples(self):
        assert extract_json("{'a': 1}") == {"a": 1}

    def test_texto_ao_redor(self):
        assert extract_json('aqui o json: {"a": 1} fim') == {"a": 1}

    def test_json_invalido_levanta_valueerror(self):
        with pytest.raises(ValueError):
            extract_json("isso nao e json")


class TestIsPctCol:
    def test_reconhece_sufixo_pct(self):
        assert _is_pct_col("variacao_pct") is True

    def test_reconhece_prefixo_pct(self):
        assert _is_pct_col("pct_total") is True

    def test_reconhece_participacao(self):
        assert _is_pct_col("participacao") is True

    def test_reconhece_atingimento(self):
        assert _is_pct_col("atingimento") is True

    def test_nao_reconhece_coluna_valor(self):
        assert _is_pct_col("valor_liquido_final") is False

    def test_nao_reconhece_total(self):
        assert _is_pct_col("total") is False


class TestFormatDf:
    def test_formata_float_como_reais(self):
        df = pd.DataFrame([{"total": 1000.50}])
        result = format_df(df)
        assert "R$" in result
        assert "1.000,50" in result

    def test_nao_formata_pct_como_reais(self):
        df = pd.DataFrame([{"participacao_pct": 45.5}])
        result = format_df(df)
        assert "R$" not in result
        assert "45.5" in result

    def test_multiplas_colunas(self):
        df = pd.DataFrame([{"casa": "TB", "total": 500.0}])
        result = format_df(df)
        assert "casa: TB" in result
        assert "R$" in result

    def test_dataframe_vazio(self):
        df = pd.DataFrame(columns=["total"])
        assert format_df(df) == ""
