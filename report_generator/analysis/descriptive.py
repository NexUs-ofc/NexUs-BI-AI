"""Análise descritiva manual (pandas): calcula o bloco `dados` do relatório a partir de um mês.

Todo número do relatório nasce aqui. Os agentes só leem e interpretam.

Premissas do MVP (ajuste aqui se o time decidir diferente):
- "qtd" em D3, D4 e D8 = nº de itens (linhas de pantry_item), não a soma de `quantity`.
- D1 conta eventos do mês (não soma `discarded_quantity`).
- Data de referência = último dia do mês. D4 conta itens que vencem de 0 a 7 dias depois dela
  (os já vencidos ficam de fora, eles entram no D3).
- D6: só conta household com mínimo > 0; ele está "abaixo" se ao menos um alimento tem quantidade
  total na despensa menor que o mínimo.
- D9 é um índice (expirados por household), não porcentagem.
- Privacidade: UF com menos de MIN_HOUSEHOLDS households tem os números omitidos.
"""
import pandas as pd

from report_generator.config import MIN_HOUSEHOLDS
from report_generator.data.loader import MonthData
from report_generator.kpis import KPIS, kpi_status
from report_generator.schemas import (
    AlimentoAbaixoMinimo,
    Base,
    Dados,
    KpiValor,
    LinhaCategoria,
    LinhaUF,
    VidaUtil,
)

TOP_ABAIXO_MINIMO = 10


def _pct(num: float, den: float) -> float | None:
    return round(100 * num / den, 1) if den else None


def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), 1)


def _kpi(codigo: str, num: float, den: float, previous: dict | None) -> KpiValor:
    kpi = KPIS[codigo]
    valor = _pct(num, den)
    anterior = (previous or {}).get("kpis", {}).get(codigo, {}).get("valor")
    variacao = round(valor - anterior, 1) if valor is not None and anterior is not None else None
    return KpiValor(codigo=codigo, nome=kpi.nome, unidade=kpi.unidade, valor=valor, meta=kpi.meta,
                    regra=kpi.regra, status=kpi_status(codigo, valor), numerador=num, denominador=den,
                    mes_anterior=anterior, variacao_pp=variacao)


def _with_expiry_flags(month: MonthData) -> pd.DataFrame:
    items = month.items.copy()
    ref = pd.Timestamp(month.data_referencia)
    items["tem_validade"] = items["expiry_date"].notna()
    days = (items["expiry_date"] - ref).dt.days
    items["vencido"] = items["tem_validade"] & (days < 0)
    items["a_vencer_7d"] = items["tem_validade"] & days.between(0, 7)
    items["a_vencer_30d"] = items["tem_validade"] & days.between(0, 30)
    items["vida_util_dias"] = (items["expiry_date"] - items["created_at"]).dt.days
    return items


def _below_minimum(month: MonthData) -> tuple[pd.DataFrame, int, int]:
    """Configurações com mínimo > 0, marcadas com `abaixo`, + (households abaixo, households com mínimo)."""
    settings = month.settings[month.settings["minimum_quantity"] > 0].copy()
    if settings.empty:
        return settings.assign(abaixo=False), 0, 0
    stock = month.items.groupby(["household_id", "food_id"], as_index=False)["quantity"].sum()
    settings = settings.merge(stock, on=["household_id", "food_id"], how="left").fillna({"quantity": 0})
    settings["abaixo"] = settings["quantity"] < settings["minimum_quantity"]
    per_household = settings.groupby("household_id")["abaixo"].any()
    return settings, int(per_household.sum()), int(per_household.size)


def _vida_util(items: pd.DataFrame, previous: dict | None) -> VidaUtil:
    days = items.loc[items["tem_validade"], "vida_util_dias"].dropna()
    prev = (previous or {}).get("vida_util", {}).get("mediana")
    if days.empty:
        return VidaUtil(itens=0, media=None, mediana=None, p25=None, p75=None, minimo=None, maximo=None,
                        outliers=0, mediana_mes_anterior=prev)
    q1, q3 = days.quantile(0.25), days.quantile(0.75)
    iqr = q3 - q1
    outliers = int(((days < q1 - 1.5 * iqr) | (days > q3 + 1.5 * iqr)).sum())
    return VidaUtil(itens=int(days.size), media=_num(days.mean()), mediana=_num(days.median()), p25=_num(q1),
                    p75=_num(q3), minimo=_num(days.min()), maximo=_num(days.max()), outliers=outliers,
                    mediana_mes_anterior=prev)


def _por_uf(items: pd.DataFrame, households: pd.DataFrame) -> list[LinhaUF]:
    count = households.groupby("uf")["household_id"].nunique()
    agg = items[items["tem_validade"]].groupby("uf").agg(
        itens_com_validade=("tem_validade", "size"), vencidos=("vencido", "sum"),
        a_vencer_30d=("a_vencer_30d", "sum"))
    rows = []
    for uf, n in count.items():
        if n < MIN_HOUSEHOLDS or uf not in agg.index:
            rows.append(LinhaUF(uf=uf, households=int(n), suprimido=True))
            continue
        a = agg.loc[uf]
        rows.append(LinhaUF(uf=uf, households=int(n), itens_com_validade=int(a.itens_com_validade),
                            vencidos=int(a.vencidos), a_vencer_30d=int(a.a_vencer_30d),
                            d3_pct_vencidos=_pct(a.vencidos, a.itens_com_validade),
                            d5_pontuacao=int(a.vencidos + a.a_vencer_30d)))
    # D5: DENSE_RANK (maior pontuação = 1º), só entre as UFs não suprimidas
    scores = sorted({r.d5_pontuacao for r in rows if not r.suprimido}, reverse=True)
    for r in rows:
        if not r.suprimido:
            r.d5_rank = scores.index(r.d5_pontuacao) + 1
    return sorted(rows, key=lambda r: (r.suprimido, r.d5_rank or 0, r.uf))


def _por_categoria(items: pd.DataFrame, events: pd.DataFrame) -> list[LinhaCategoria]:
    expired = events[events["event_type"] == "item_expired"].groupby("categoria").size()
    rows = []
    for cat, group in items.groupby("categoria"):
        valid = group[group["tem_validade"]]
        n_hh = int(group["household_id"].nunique())
        exp = int(expired.get(cat, 0))
        rows.append(LinhaCategoria(
            categoria=cat, itens_com_validade=len(valid), households_com_categoria=n_hh,
            d4_pct_a_vencer_7d=_pct(valid["a_vencer_7d"].sum(), len(valid)), expirados_no_mes=exp,
            d9_indice_desperdicio=round(exp / n_hh, 2) if n_hh else None,
            d7_mediana_dias=_num(valid["vida_util_dias"].median()),
            d5_pontuacao=int(valid["vencido"].sum() + valid["a_vencer_30d"].sum())))
    return sorted(rows, key=lambda r: -(r.d9_indice_desperdicio or 0))


def build_dados(month: MonthData, previous: dict | None = None) -> Dados:
    """Calcula o bloco `dados`. `previous` = bloco `dados` do mês anterior (do Mongo), para as variações."""
    items = _with_expiry_flags(month)
    events = month.events
    valid = items[items["tem_validade"]]

    expired = int((events["event_type"] == "item_expired").sum())
    consumed = int((events["event_type"] == "item_consumed").sum())
    settings, hh_below, hh_with_min = _below_minimum(month)

    kpis = {
        "D1": _kpi("D1", expired, expired + consumed, previous),
        "D3": _kpi("D3", int(valid["vencido"].sum()), len(valid), previous),
        "D4": _kpi("D4", int(valid["a_vencer_7d"].sum()), len(valid), previous),
        "D6": _kpi("D6", hh_below, hh_with_min, previous),
        "D8": _kpi("D8", int((~items["tem_validade"]).sum()), len(items), previous),
    }

    below = settings[settings["abaixo"]] if not settings.empty else settings
    top = (below.groupby(["alimento", "categoria"])["household_id"].nunique()
           .sort_values(ascending=False).head(TOP_ABAIXO_MINIMO)) if not below.empty else pd.Series(dtype=int)

    return Dados(
        base=Base(households=int(month.households["household_id"].nunique()), itens_na_despensa=len(items),
                  eventos_no_mes=len(events), data_referencia=month.data_referencia.isoformat()),
        kpis=kpis,
        vida_util=_vida_util(items, previous),
        por_uf=_por_uf(items, month.households),
        por_categoria=_por_categoria(items, events),
        top_abaixo_minimo=[AlimentoAbaixoMinimo(alimento=a, categoria=c, households=int(n))
                           for (a, c), n in top.items()],
    )
