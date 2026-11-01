"""Catálogo dos KPIs do relatório: nome, fórmula, unidade e meta.

É a única fonte dessas definições: a análise, os prompts, o template e o dashboard devem usar estes
códigos (D1, D3...). Metas e fórmulas seguem as tabelas Gold do Databricks (workspace.gold.kpi_cards),
que são a fonte oficial. Para mudar uma meta, altere aqui e na Gold.

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
        KpiDef("D1", "Taxa de desperdício", "unidades descartadas ÷ unidades que saíram da despensa (consumidas + descartadas), no mês",
               "%", 15.0, "<=", descricao_card="Indicador com meta"),
        KpiDef("D2", "Descarte por esquecimento", "unidades descartadas mais de 7 dias depois de vencer ÷ unidades descartadas com validade, no mês",
               "%"),
        KpiDef("D3", "Itens vencidos na despensa", "unidades vencidas ÷ unidades com validade (foto da despensa)", "%", 5.0, "<=",
               descricao_card="Indicador com meta"),
        KpiDef("D4", "Itens que vencem em 7 dias", "unidades que vencem em até 7 dias ÷ unidades com validade (foto da despensa)", "%", 10.0,
               "<=",
               tipo_meta="alerta", descricao_card="Alerta acima do limite"),
        KpiDef("D5", "Risco de vencimento por estado",
               "% das unidades vencidas ou vencendo em até 30 dias, por UF (1 = maior risco; UFs com amostra pequena "
               "ficam fora)", "rank"),
        KpiDef("D6", "Casas abaixo do estoque mínimo", "casas com algum item abaixo do mínimo ÷ casas com mínimo configurado (foto da despensa)", "%",
               30.0, "<=", descricao_card="Controle de reposição"),
        KpiDef("D7", "Prazo de validade cadastrado", "mediana de dias entre a entrada do lote e a validade", "dias"),
        KpiDef("D8", "Itens sem validade cadastrada", "unidades sem validade ÷ todas as unidades (foto da despensa)", "%", 10.0, "<=",
               descricao_card="Qualidade de cadastro"),
        KpiDef("D9", "Desperdício por categoria",
               "unidades descartadas da categoria no mês ÷ casas que movimentaram a categoria no mês", "unid./casa"),
    ]
}

# KPIs de valor único (aparecem como cards e têm histórico mês a mês)
CARD_KPIS = ["D1", "D3", "D4", "D6", "D8"]
# KPIs de EVENTO (consumo/descarte no mês, via fato_movimento): existem em qualquer mês com movimento.
EVENT_KPIS = ["D1", "D2", "D9"]
# KPIs de ESTADO (dependem da foto da despensa): só existem em meses com foto.
STATE_KPIS = ["D3", "D4", "D5", "D6", "D7", "D8"]
# Cards com meta, por seção do relatório
EVENT_CARDS = ["D1"]
STATE_CARDS = ["D3", "D4", "D6", "D8"]


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
