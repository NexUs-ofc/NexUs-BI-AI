"""Catálogo dos KPIs do relatório: nome, fórmula, unidade e meta.

É a única fonte dessas definições: a análise, os prompts, o template e o dashboard devem usar estes
códigos (D1, D3...). Para mudar uma meta, altere só aqui.

regra: "<=" quer dizer que o valor deve ficar ATÉ a meta (todos os KPIs atuais são "quanto menor, melhor").
tipo_meta: "meta" (fora dela = acima_da_meta) ou "alerta" (D4: fora dela = alerta).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class KpiDef:
    codigo: str
    nome: str
    formula: str
    unidade: str  # "%", "dias" ou "indice"
    meta: float | None = None
    regra: str | None = None
    tipo_meta: str = "meta"
    descricao_card: str = ""


KPIS: dict[str, KpiDef] = {
    k.codigo: k
    for k in [
        KpiDef("D1", "Taxa de desperdício", "item_expired / (item_expired + item_consumed)", "%", 15.0, "<=",
               descricao_card="Indicador com meta"),
        KpiDef("D3", "% itens vencidos na despensa", "qtd vencida / qtd com validade", "%", 5.0, "<=",
               descricao_card="Indicador com meta"),
        KpiDef("D4", "% a vencer em 7 dias", "qtd com validade em até 7 dias / qtd com validade", "%", 10.0, "<=",
               tipo_meta="alerta", descricao_card="Alerta acima do limite"),
        KpiDef("D5", "Ranking de vencimento por UF", "DENSE_RANK por UF de (vencidos + a vencer em 30 dias)", "rank"),
        KpiDef("D6", "Estoque abaixo do mínimo", "households abaixo / households com mínimo configurado", "%",
               20.0, "<=", descricao_card="Controle de reposição"),
        KpiDef("D7", "Vida útil no cadastro", "expiry_date - created_at (dias)", "dias"),
        KpiDef("D8", "% itens sem validade", "COUNT(expiry_date IS NULL) / COUNT(*)", "%", 5.0, "<=",
               descricao_card="Qualidade de cadastro"),
        KpiDef("D9", "Índice de desperdício por categoria", "expirados da categoria / households com a categoria",
               "indice"),
    ]
}

# KPIs de valor único (aparecem como cards e têm histórico mês a mês)
CARD_KPIS = ["D1", "D3", "D4", "D6", "D8"]


def kpi_status(codigo: str, valor: float | None) -> str:
    """dentro_meta | acima_da_meta | alerta | sem_meta | sem_dados (calculado por código, nunca pelo LLM)."""
    kpi = KPIS[codigo]
    if valor is None:
        return "sem_dados"
    if kpi.meta is None:
        return "sem_meta"
    ok = valor <= kpi.meta if kpi.regra == "<=" else valor >= kpi.meta
    if ok:
        return "dentro_meta"
    return "alerta" if kpi.tipo_meta == "alerta" else "acima_da_meta"
