"""Narrativa sem IA, montada por regras a partir de `dados`.

Serve para rodar o pipeline sem GOOGLE_API_KEY (testes, CI, desenvolvimento do template). Não substitui
os agentes: o texto é propositalmente simples. Indicadores de estado (despensa) só entram quando o mês tem
foto da despensa.
"""
from report_generator.formatting import br, integer, pct, pp
from report_generator.kpis import CARD_KPIS
from report_generator.schemas import AnaliseKpi, Dados, Insight, Narrativa

STATUS_TEXT = {"dentro_meta": "dentro da meta", "acima_da_meta": "acima da meta", "alerta": "acima do limite de alerta"}


def _card_text(dados: Dados, codigo: str, periodo: str) -> str:
    k = dados.kpis[codigo]
    if k.valor is None:
        return f"{k.nome} em {periodo}: dado não disponível."
    base = f" ({integer(k.numerador)} de {integer(k.denominador)})" if k.numerador is not None else ""
    text = (f"{k.nome} em {periodo}: {pct(k.valor)}{base}, "
            f"{STATUS_TEXT.get(k.status, 'sem meta')} (meta de até {pct(k.meta)}).")
    if k.variacao_pp is not None:
        text += f" Variação contra o mês anterior: {pp(k.variacao_pp)}"
    return text


def build_fallback_narrative(dados: Dados, history: list[dict], periodo: str) -> Narrativa:
    cats = dados.desperdicio_categoria or []
    worst_cat = cats[0] if cats else None
    cards = [c for c in CARD_KPIS if c in dados.kpis and (dados.tem_despensa or c == "D1")]
    off_target = [dados.kpis[c] for c in cards if dados.kpis[c].status in ("acima_da_meta", "alerta")]
    ate_agora = " até agora" if dados.parcial else ""

    analise = [AnaliseKpi(kpi="D1", texto=_card_text(dados, "D1", periodo))]
    d2 = dados.kpis.get("D2")
    if d2 and d2.valor is not None:
        analise.append(AnaliseKpi(kpi="D2", texto=(
            f"{pct(d2.valor)} das unidades descartadas com validade foram descartadas mais de 7 dias depois "
            f"de vencer.")))
    if worst_cat:
        analise.append(AnaliseKpi(kpi="D9", texto=(
            f"{worst_cat.categoria} tem o maior desperdício por casa no período: {br(worst_cat.d9_indice, 2)} "
            f"unidade descartada por casa ({pct(worst_cat.pct_do_desperdicio)} de tudo o que foi descartado).")))

    if dados.tem_despensa:
        ufs = [u for u in dados.por_uf if not u.suprimido]
        suppressed = [u.uf for u in dados.por_uf if u.suprimido]
        vu = dados.vida_util
        analise += [AnaliseKpi(kpi=c, texto=_card_text(dados, c, periodo)) for c in ("D3", "D4")]
        if ufs:
            top3 = ", ".join(f"{u.uf} ({u.d5_rank}º)" for u in ufs[:3])
            d5 = f"Os estados mais críticos em vencimento são {top3}."
            if suppressed:
                d5 += f" Sem dados suficientes (privacidade): {', '.join(suppressed)}."
            analise.append(AnaliseKpi(kpi="D5", texto=d5))
        analise.append(AnaliseKpi(kpi="D6", texto=_card_text(dados, "D6", periodo)))
        if vu.mediana is not None and vu.p25 is not None:
            d7 = (f"O prazo de validade cadastrado tem mediana de {integer(vu.mediana)} dias (de {integer(vu.p25)} a "
                  f"{integer(vu.p75)} dias entre o 1º e o 3º quartil), com {integer(vu.outliers)} outliers.")
        else:
            d7 = f"O prazo de validade cadastrado tem média de {integer(vu.media)} dias."
        analise.append(AnaliseKpi(kpi="D7", texto=d7))
        analise.append(AnaliseKpi(kpi="D8", texto=_card_text(dados, "D8", periodo)))

    insights = [Insight(tipo="alerta", titulo=f"{k.nome} fora da meta",
                        texto=_card_text(dados, k.codigo, periodo), kpis=[k.codigo]) for k in off_target]
    if worst_cat:
        insights.append(Insight(tipo="destaque", titulo=f"{worst_cat.categoria} concentra o desperdício",
                                texto=f"{worst_cat.categoria} tem o maior desperdício por casa "
                                      f"({br(worst_cat.d9_indice, 2)} unidade descartada por casa).", kpis=["D9"]))

    r = dados.resumo
    partes = []
    if r and r.unidades_saidas is not None:
        partes.append(f"{integer(r.unidades_saidas)} unidades saíram da despensa, "
                      f"{integer(r.unidades_descartadas)} foram descartadas")
    if r and r.casas_com_movimento is not None:
        partes.append(f"{integer(r.casas_com_movimento)} casas tiveram movimento")
    resumo = f"Em {periodo}{ate_agora}: {'; '.join(partes)}. " if partes else f"Relatório de {periodo}{ate_agora}. "
    resumo += (f"{len(off_target)} indicador(es) ficaram fora da meta: {', '.join(k.nome for k in off_target)}."
               if off_target else "Todos os indicadores com meta ficaram dentro dela.")

    limitacoes = ["Narrativa gerada sem IA (modo --sem-ia): textos simplificados."]
    if not dados.tem_despensa:
        limitacoes.append("Este período não tem foto da despensa: o relatório traz só os indicadores de consumo "
                          "e descarte do mês.")
    if dados.parcial:
        limitacoes.append("Mês em andamento: os números são parciais e mudam a cada atualização diária.")
    if not history:
        limitacoes.append("Não há relatórios anteriores na base; não foi possível avaliar tendências.")
    return Narrativa(resumo_executivo=resumo, analise_por_kpi=analise, insights=insights,
                     recomendacoes=["Revisar os indicadores fora da meta com as equipes responsáveis."],
                     limitacoes=limitacoes)
