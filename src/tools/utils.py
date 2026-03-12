import re

import pandas as pd


def strip_markdown(query: str) -> str:
    """Remove blocos de markdown (```sql ... ```) que o agente pode gerar."""
    query = query.strip()
    query = re.sub(r'^```\w*\s*', '', query)
    query = re.sub(r'\s*```$', '', query)
    return query.strip()


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
