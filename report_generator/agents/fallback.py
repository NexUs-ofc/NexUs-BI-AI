"""Narrativa sem IA, montada por regras a partir de `dados`.

Serve para rodar o pipeline sem GOOGLE_API_KEY (testes, CI, desenvolvimento do template). Não substitui
os agentes: o texto é propositalmente simples.
"""
from report_generator.formatting import integer, pct, pp
from report_generator.kpis import CARD_KPIS
from report_generator.schemas import AnaliseKpi, Dados, Insight, Narrativa

STATUS_TEXT = {"dentro_meta": "dentro da meta", "acima_da_meta": "acima da meta", "alerta": "acima do limite de alerta"}


def _card_text(dados: Dados, codigo: str, periodo: str) -> str:
    k = dados.kpis[codigo]
    text = (f"{k.nome} em {periodo}: {pct(k.valor)} ({integer(k.numerador)} de {integer(k.denominador)}), "
            f"{STATUS_TEXT.get(k.status, 'sem meta')} (meta de até {pct(k.meta)}).")
    if k.variacao_pp is not None:
        text += f" Variação contra o mês anterior: {pp(k.variacao_pp)}"
    return text


def build_fallback_narrative(dados: Dados, history: list[dict], periodo: str) -> Narrativa:
    ufs = [u for u in dados.por_uf if not u.suprimido]
    suppressed = [u.uf for u in dados.por_uf if u.suprimido]
    cats = dados.por_categoria
    worst_cat = cats[0] if cats else None
    vu = dados.vida_util
    off_target = [dados.kpis[c] for c in CARD_KPIS if dados.kpis[c].status in ("acima_da_meta", "alerta")]

    analise = [AnaliseKpi(kpi=c, texto=_card_text(dados, c, periodo)) for c in ("D1", "D3", "D4")]
    top3 = ", ".join(f"{u.uf} ({u.d5_rank}º)" for u in ufs[:3])
    d5 = f"As UFs mais críticas em vencimento são {top3}."
    if suppressed:
        d5 += f" Sem dados suficientes (privacidade): {', '.join(suppressed)}."
    analise.append(AnaliseKpi(kpi="D5", texto=d5))
    analise.append(AnaliseKpi(kpi="D6", texto=_card_text(dados, "D6", periodo)))
    analise.append(AnaliseKpi(kpi="D7", texto=(
        f"A vida útil cadastrada tem mediana de {integer(vu.mediana)} dias (de {integer(vu.p25)} a "
        f"{integer(vu.p75)} dias entre o 1º e o 3º quartil), com {integer(vu.outliers)} outliers.")))
    analise.append(AnaliseKpi(kpi="D8", texto=_card_text(dados, "D8", periodo)))
    if worst_cat:
        analise.append(AnaliseKpi(kpi="D9", texto=(
            f"{worst_cat.categoria} tem o maior índice de desperdício: "
            f"{str(worst_cat.d9_indice_desperdicio).replace('.', ',')} item vencido por household.")))

    insights = [Insight(tipo="alerta", titulo=f"{k.nome} fora da meta",
                        texto=_card_text(dados, k.codigo, periodo), kpis=[k.codigo]) for k in off_target]
    if worst_cat:
        insights.append(Insight(tipo="destaque", titulo=f"{worst_cat.categoria} concentra o desperdício",
                                texto=f"{worst_cat.categoria} registrou {integer(worst_cat.expirados_no_mes)} "
                                      f"itens vencidos no mês.", kpis=["D9"]))

    resumo = (f"Em {periodo}, a base teve {integer(dados.base.households)} households, "
              f"{integer(dados.base.itens_na_despensa)} itens na despensa e {integer(dados.base.eventos_no_mes)} "
              f"eventos de consumo ou vencimento. ")
    resumo += (f"{len(off_target)} KPI(s) ficaram fora da meta: {', '.join(k.nome for k in off_target)}."
               if off_target else "Todos os KPIs com meta ficaram dentro dela.")

    limitacoes = ["Narrativa gerada sem IA (modo --sem-ia): textos simplificados."]
    if not history:
        limitacoes.append("Não há relatórios anteriores na base; não foi possível avaliar tendências.")
    return Narrativa(resumo_executivo=resumo, analise_por_kpi=analise, insights=insights,
                     recomendacoes=["Revisar os KPIs fora da meta com as equipes responsáveis."],
                     limitacoes=limitacoes)
