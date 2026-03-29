import json
import re

import pandas as pd


def strip_markdown(query: str) -> str:
    """Remove blocos de markdown e JSON wrappers que o agente pode gerar."""
    query = query.strip()
    query = re.sub(r'^```\w*\s*|\s*```$', '', query)
    query = query.strip()
    if query.startswith('{'):
        try:
            parsed = json.loads(query)
            for key in ("sql", "SQL", "query", "QUERY"):
                if key in parsed:
                    query = parsed[key].strip()
                    break
        except (json.JSONDecodeError, AttributeError):
            pass
    return query


def extract_json(text: str) -> dict:
    """
    Extrai e parseia JSON de uma string que pode conter texto extra ao redor.
    Corrige problemas comuns do Grok: trailing commas, aspas simples, texto antes/depois do JSON.
    """
    text = text.strip()
    text = re.sub(r'^```\w*\s*|\s*```$', '', text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL)
    if match:
        text = match.group(0)

    # trailing commas são comuns no Grok — corrige antes de parsear
    text = re.sub(r',\s*([}\]])', r'\1', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # última tentativa: aspas simples → duplas
    try:
        text_fixed = text.replace("'", '"')
        return json.loads(text_fixed)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalido mesmo apos correcoes: {e}") from e


_PCT_KEYWORDS = ("_pct", "pct_", "percent", "participacao", "atingimento", "variacao_pct", "delta_pct")


def _is_pct_col(col: str) -> bool:
    col_lower = col.lower()
    return any(kw in col_lower for kw in _PCT_KEYWORDS)


def format_df(df: pd.DataFrame) -> str:
    """Formata DataFrame como texto limpo e legível para o LLM."""
    rows = []
    for record in df.to_dict("records"):
        parts = []
        for col, val in record.items():
            if isinstance(val, float) and not _is_pct_col(col):
                formatted = f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                parts.append(f"{col}: {formatted}")
            else:
                parts.append(f"{col}: {val}")
        rows.append(" | ".join(parts))
    return "\n".join(rows)
