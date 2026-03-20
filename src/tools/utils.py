import json
import re

import pandas as pd


def strip_markdown(query: str) -> str:
    """Remove blocos de markdown e JSON wrappers que o agente pode gerar."""
    query = query.strip()
    # Remove blocos de markdown ```sql ... ```
    query = re.sub(r'^```\w*\s*', '', query)
    query = re.sub(r'\s*```$', '', query)
    query = query.strip()
    # Se o modelo retornou JSON (ex: {"SQL": "SELECT ..."} ou {"sql": "..."}), extrai o valor
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

    # Remove blocos de markdown ```json ... ```
    text = re.sub(r'^```\w*\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()

    # Tenta parsear diretamente primeiro (mais rápido para inputs bem formados)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extrai o primeiro objeto JSON { ... } da string, sem ser greedy além do necessário
    # re.DOTALL permite newlines; o padrão evita capturar desde o primeiro { até o último }
    match = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL)
    if match:
        text = match.group(0)

    # Corrige trailing commas antes de } ou ] (JSON invalido mas comum no Grok)
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Tenta parsear diretamente
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Ultima tentativa: aspas simples → duplas
    try:
        text_fixed = text.replace("'", '"')
        return json.loads(text_fixed)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalido mesmo apos correcoes: {e}") from e


def format_df(df: pd.DataFrame) -> str:
    """Formata DataFrame como texto limpo e legível para o LLM."""
    rows = []
    for record in df.to_dict("records"):
        parts = []
        for col, val in record.items():
            if isinstance(val, float) and not col.lower().endswith("_pct"):
                formatted = f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                parts.append(f"{col}: {formatted}")
            else:
                parts.append(f"{col}: {val}")
        rows.append(" | ".join(parts))
    return "\n".join(rows)
