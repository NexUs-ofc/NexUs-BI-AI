"""Tool usada pelo Analista e pelo Recomendador: resumo descritivo da base.

Os números são calculados em código (pandas); a LLM só interpreta.
"""
import pandas as pd

from app.repository.dados_repository import carregar_base, nome_base


def resumo_base() -> str:
    try:
        df = carregar_base()
    except Exception as e:  # noqa: BLE001
        return f"ERRO_BASE: {e}"

    partes = [
        f"Arquivo: {nome_base()}",
        f"Linhas: {len(df)} | Colunas: {', '.join(df.columns)}",
    ]

    numericas = df.select_dtypes("number").columns.tolist()
    colunas_data = [c for c in df.columns if c.lower() in ("data", "date", "dt")]
    categoricas = [c for c in df.select_dtypes(exclude="number").columns if c not in colunas_data]

    if numericas:
        desc = df[numericas].describe().round(2)
        partes.append("Estatísticas numéricas:\n" + desc.to_string())
        partes.append("Totais: " + ", ".join(f"{c}={df[c].sum():,.2f}" for c in numericas))

    metrica = numericas[-1] if numericas else None
    for col in categoricas:
        if df[col].nunique() > 30:
            continue  # evita colunas tipo id com muitos valores
        if metrica:
            agg = df.groupby(col)[metrica].agg(["sum", "count"]).sort_values("sum", ascending=False)
            agg["%_total"] = (agg["sum"] / agg["sum"].sum() * 100).round(1)
            partes.append(f"{metrica} por {col}:\n" + agg.to_string())
        else:
            partes.append(f"Contagem por {col}:\n" + df[col].value_counts().to_string())

    # Série temporal simples se existir coluna de data
    if colunas_data and metrica:
        tmp = df.copy()
        tmp["mes"] = pd.to_datetime(tmp[colunas_data[0]], errors="coerce").dt.to_period("M").astype(str)
        partes.append(f"{metrica} por mês:\n" + tmp.groupby("mes")[metrica].sum().to_string())

    return "\n\n".join(partes)
