"""Gold do Databricks -> bloco `dados` do relatório e JSON do Dashboard do site.

A Gold já traz os KPIs oficiais calculados; aqui só se reorganiza para os contratos existentes
(schemas.Dados e o DashboardData do NexUs-Web). Regras:
- Percentuais chegam com 2 casas e são arredondados para 1 (o padrão do relatório e da checagem de números).
- Indicadores de EVENTO (taxa de desperdício, descarte por esquecimento, categorias, regiões, momento do
  descarte) vêm do mês pedido: kpi_desperdicio_mensal e consultas agregadas em fato_movimento (ano_mes_evento).
  Indicadores de ESTADO (D3, D4, D6, D7, D8, UF) vêm da última foto da despensa do mês (kpi_estado_diario);
  sem foto no mês, `tem_despensa=False` e eles ficam fora do relatório.
- UF com menos de MIN_LOTES_UF lotes fica fora do ranking e do mapa (regra do card D5 na Gold).
- Contagens por UF (vencidos, a vencer em 30 dias) são DERIVADAS dos percentuais oficiais.
- Households, quartis/histograma de vida útil, D4 por categoria, categoria x região e alimentos abaixo do
  mínimo vêm das tabelas fato_* já agregadas no warehouse (gold.fatos, veja data/databricks.py).
- kpi_uf só tem a foto de HOJE (sem série histórica): usada só quando o mês pedido é o mês dessa foto
  (`_foto_do_mes`); para um mês fechado mais antigo, por_uf fica vazio em vez de mostrar dados de hoje com a
  etiqueta de outro mês.
- D9 (desperdício por categoria) é MENSAL: unidades descartadas da categoria no mês ÷ casas que
  movimentaram a categoria no mês (evento_categoria), e não mais o acumulado da kpi_categoria.
"""
from datetime import date, datetime

import pandas as pd

from report_generator.analysis.dashboard import (
    LEVELS,
    MONTHS_SHORT,
    REGIONS,
    SHELF_LIFE_BUCKETS,
    TOP_CATEGORIES,
    TOP_WASTE_CATEGORIES,
    UF_NAME,
    UF_REGION,
    quartile_levels,
    slug,
)
from report_generator.analysis.descriptive import make_kpi, rank_uf_by_risk
from report_generator.config import BRAZIL_TZ, MIN_LOTES_UF
from report_generator.data.databricks import GoldData, ano_mes
from report_generator.data.loader import last_day
from report_generator.schemas import (
    AlimentoAbaixoMinimo,
    Base,
    Dados,
    DesperdicioCategoria,
    DesperdicioRegiao,
    LinhaCategoria,
    LinhaUF,
    MomentoDescarte,
    PontoMensal,
    ResumoMes,
    VidaUtil,
)

SEM_CATEGORIA = "Não informada"
EVOLUCAO_MESES = 6  # meses da evolução da taxa de desperdício e do descarte por esquecimento
_REGION_ALIASES = {"n": "norte", "norte": "norte", "ne": "nordeste", "nordeste": "nordeste",
                   "co": "centro-oeste", "centro-oeste": "centro-oeste", "centrooeste": "centro-oeste",
                   "centro oeste": "centro-oeste", "se": "sudeste", "sudeste": "sudeste", "s": "sul", "sul": "sul"}


def _num(value, decimals: int = 1) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), decimals)


def _int(value) -> int | None:
    return None if value is None or pd.isna(value) else round(float(value))


def _row(df: pd.DataFrame, **match) -> pd.Series | None:
    for col, val in match.items():
        df = df[df[col] == val]
    return None if df.empty else df.iloc[-1]


def _get(row: pd.Series | None, col: str, decimals: int = 1) -> float | None:
    return None if row is None else _num(row.get(col), decimals)


def _region(value, uf: str) -> str | None:
    key = str(value or "").strip().lower()
    return _REGION_ALIASES.get(key) or UF_REGION.get(uf)


def _derived_counts(r: pd.Series) -> tuple[int | None, int | None, int | None]:
    """(com validade, vencidos, a vencer em 30 dias) a partir de unidades e dos % oficiais da UF."""
    unidades, d3, d8, risco = r.get("unidades"), r.get("d3_vencidos_pct"), r.get("d8_sem_validade_pct"), \
        r.get("unidades_em_risco")
    if any(v is None or pd.isna(v) for v in (unidades, d3, d8, risco)):
        return None, None, None
    com_validade = round(float(unidades) * (1 - float(d8) / 100))
    vencidos = min(round(com_validade * float(d3) / 100), int(risco))
    return com_validade, vencidos, int(risco) - vencidos


def _foto_do_mes(gold: GoldData) -> bool:
    """kpi_uf só guarda UMA foto (a de hoje, no dia em que a Gold roda) — não têm série
    histórica. Usar essa foto pra um mês diferente do mês dela mostraria dados de hoje como se fossem
    daquele mês (ex.: gerar setembro depois que outubro já virou foto). Só usa quando bate com o mês pedido."""
    if not gold.data_foto:
        return False
    try:
        ano, mes = (int(x) for x in gold.data_foto.split("-")[:2])
    except ValueError:
        return False
    return (ano, mes) == (gold.ano, gold.mes)


def _por_uf(uf: pd.DataFrame) -> list[LinhaUF]:
    rows = []
    for _, r in uf.iterrows():
        sigla = str(r["uf"]).strip().upper()
        if pd.isna(r["lotes"]) or r["lotes"] < MIN_LOTES_UF:
            rows.append(LinhaUF(uf=sigla, suprimido=True))
            continue
        com_validade, vencidos, a_vencer = _derived_counts(r)
        rows.append(LinhaUF(uf=sigla, itens_com_validade=com_validade, vencidos=vencidos, a_vencer_30d=a_vencer,
                            d3_pct_vencidos=_num(r["d3_vencidos_pct"]), d5_pontuacao=_int(r["unidades_em_risco"]),
                            d5_pct_em_risco=_num(r["pct_em_risco"])))
    rank_uf_by_risk(rows)
    return sorted(rows, key=lambda r: (r.suprimido, r.d5_rank or 0, r.uf))


def _known(df: pd.DataFrame) -> pd.DataFrame:
    """Só categorias conhecidas ("Não informada" / "Não informado(a)" ficam de fora dos rankings)."""
    nome = df["categoria"].fillna(SEM_CATEGORIA).astype(str)
    return df[~nome.str.lower().str.startswith("não informad")]


def _pct(part, total) -> float | None:
    return None if total is None or pd.isna(total) or not total else round(100 * float(part or 0) / float(total), 1)


def _first(df: pd.DataFrame) -> pd.Series | None:
    return None if df.empty else df.iloc[0]


def _desperdicio_categoria(df: pd.DataFrame) -> list[DesperdicioCategoria]:
    """Evento do mês por categoria. D9 = unidades descartadas ÷ casas que movimentaram a categoria no mês."""
    total = float(df["unidades_descartadas"].fillna(0).sum()) if not df.empty else 0.0
    rows = []
    for _, r in _known(df).iterrows():
        descartadas, saidas, casas = (_int(r[c]) or 0 for c in ("unidades_descartadas", "unidades_saidas", "casas"))
        rows.append(DesperdicioCategoria(
            categoria=r["categoria"], unidades_descartadas=descartadas, unidades_saidas=saidas, casas=casas,
            d1_pct=_pct(descartadas, saidas), d9_indice=round(descartadas / casas, 2) if casas else None,
            pct_do_desperdicio=_pct(descartadas, total)))
    return sorted(rows, key=lambda r: (-(r.d9_indice or 0), r.categoria))


def _desperdicio_regiao(df: pd.DataFrame) -> list[DesperdicioRegiao]:
    """D1 e D2 por região (soma as linhas que caem na mesma região)."""
    acc: dict[str, dict[str, float]] = {}
    for _, r in df.iterrows():
        rid = _region(r["regiao"], "")
        if rid is None:
            continue
        a = acc.setdefault(rid, dict.fromkeys(("desc", "saidas", "com_validade", "esquecidas"), 0.0))
        a["desc"] += float(r["unidades_descartadas"] or 0)
        a["saidas"] += float(r["unidades_saidas"] or 0)
        a["com_validade"] += float(r["descartadas_com_validade"] or 0) if not pd.isna(r["descartadas_com_validade"]) else 0
        a["esquecidas"] += float(r["esquecidas"] or 0) if not pd.isna(r["esquecidas"]) else 0
    names = {rid: name for rid, name, _ in REGIONS}
    rows = [DesperdicioRegiao(regiao=names.get(rid, rid.title()), unidades_descartadas=round(a["desc"]),
                              unidades_saidas=round(a["saidas"]), d1_pct=_pct(a["desc"], a["saidas"]),
                              d2_pct=_pct(a["esquecidas"], a["com_validade"]))
            for rid, a in acc.items()]
    return sorted(rows, key=lambda r: -(r.d1_pct or 0))


_MOMENTO_LABEL = {"1": "Antes de vencer", "2": "Até 7 dias depois de vencer", "3": "Esquecido (mais de 7 dias depois)",
                  "4": "Sem validade cadastrada"}


def _momento_descarte(df: pd.DataFrame) -> list[MomentoDescarte]:
    total = float(df["unidades"].fillna(0).sum()) if not df.empty else 0.0
    rows = []
    for _, r in df.iterrows():
        key = str(r["momento"] or "").strip()[:1]
        if key not in _MOMENTO_LABEL or not (r["unidades"] or 0):
            continue
        rows.append((key, MomentoDescarte(momento=_MOMENTO_LABEL[key], unidades=_int(r["unidades"]) or 0,
                                          pct=_pct(r["unidades"], total))))
    return [m for _, m in sorted(rows, key=lambda x: x[0])]


def _evolucao(mensal: pd.DataFrame, meses: int = EVOLUCAO_MESES) -> list[PontoMensal]:
    """Taxa de desperdício e descarte por esquecimento dos últimos meses (kpi_desperdicio_mensal)."""
    rows = []
    for _, r in mensal.tail(meses).iterrows():
        rows.append(PontoMensal(ano_mes=str(r["ano_mes"]), d1=_num(r["d1_pct"]), d2=_num(r["d2_esquecidos_pct"]),
                                completo=bool(r["mes_completo"]) if not pd.isna(r["mes_completo"]) else True))
    return rows


def _por_categoria(eventos: list[DesperdicioCategoria], estoque: pd.DataFrame) -> list[LinhaCategoria]:
    """Visão por categoria: desperdício do MÊS (evento) + validade da despensa (estado, se houver foto)."""
    stock = {r["categoria"]: r for _, r in _known(estoque).iterrows()}
    by_event = {e.categoria: e for e in eventos}
    rows = []
    for nome in sorted({*by_event, *stock}):
        e, s = by_event.get(nome), stock.get(nome)
        rows.append(LinhaCategoria(
            categoria=nome, households_com_categoria=e.casas if e else None,
            itens_com_validade=_int(s["unidades_com_validade"]) if s is not None else None,
            d4_pct_a_vencer_7d=_pct(s["unidades_7d"], s["unidades_com_validade"]) if s is not None else None,
            expirados_no_mes=e.unidades_descartadas if e else None, d9_indice_desperdicio=e.d9_indice if e else None,
            d7_mediana_dias=_num(s["mediana"]) if s is not None else None,
            pct_do_desperdicio=e.pct_do_desperdicio if e else None))
    return sorted(rows, key=lambda r: -(r.d9_indice_desperdicio or 0))


def _resumo(gold: GoldData, kpis: dict) -> ResumoMes:
    r = _first(gold.fatos["evento_resumo"])
    avaliados = [k for k in kpis.values() if k.meta is not None and k.valor is not None]
    fora = [k for k in avaliados if k.status in ("acima_da_meta", "alerta")]
    return ResumoMes(unidades_saidas=_int(r["unidades_saidas"]) if r is not None else None,
                     unidades_descartadas=_int(r["unidades_descartadas"]) if r is not None else None,
                     casas_com_movimento=_int(r["casas"]) if r is not None else None,
                     avaliados=len(avaliados), fora_da_meta=len(fora))


def gold_to_dados(gold: GoldData, previous: dict | None = None, hoje: date | None = None) -> Dados:
    """`previous` = bloco `dados` do mês anterior (Mongo), para a variação dos KPIs de estado.

    Dois grupos de indicadores:
    - EVENTO (taxa de desperdício, descarte por esquecimento, categorias, regiões, momento do descarte):
      filtrados pelo mês do evento em fato_movimento; existem em qualquer mês com movimento.
    - ESTADO (vencidos, a vencer, sem validade, abaixo do mínimo, vida útil, UF): dependem da foto da
      despensa. Sem foto no mês, `tem_despensa=False` e esses indicadores ficam vazios (e fora do relatório).
    """
    hoje = hoje or datetime.now(BRAZIL_TZ).date()
    am = ano_mes(gold.ano, gold.mes)
    mes = _row(gold.mensal, ano_mes=am)
    anterior = gold.mensal[gold.mensal["ano_mes"] < am]
    anterior = anterior.iloc[-1] if not anterior.empty else None
    tem_despensa = not gold.estado.empty
    estado = gold.estado.iloc[0] if tem_despensa else None
    prev_vida = ((previous or {}).get("vida_util") or {}).get("mediana")
    total = _first(gold.fatos["estoque_total"]) if tem_despensa else None
    resumo_ev = _first(gold.fatos["evento_resumo"])

    kpis = {
        "D1": make_kpi("D1", _get(mes, "d1_pct"), previous, _get(mes, "unidades_descartadas", 0),
                       _get(mes, "unidades_movimentadas", 0), _get(anterior, "d1_pct")),
        "D2": make_kpi("D2", _get(mes, "d2_esquecidos_pct"), previous, anterior=_get(anterior, "d2_esquecidos_pct")),
        "D3": make_kpi("D3", _get(estado, "d3_vencidos_pct"), previous),
        "D4": make_kpi("D4", _get(estado, "d4_vencem_7d_pct"), previous),
        "D6": make_kpi("D6", _get(estado, "d6_abaixo_minimo_pct"), previous),
        "D8": make_kpi("D8", _get(estado, "d8_sem_validade_pct"), previous),
    }
    ref = str(estado["data_referencia"]) if estado is not None else last_day(gold.ano, gold.mes).isoformat()
    eventos_categoria = _desperdicio_categoria(gold.fatos["evento_categoria"])
    usa_foto_uf = tem_despensa and _foto_do_mes(gold)
    return Dados(
        base=Base(households=_int(total["households"]) if total is not None else None,
                  itens_na_despensa=_int(estado["unidades"]) if estado is not None else None,
                  eventos_no_mes=_int(resumo_ev["operacoes"]) if resumo_ev is not None
                  else (_int(mes["operacoes"]) if mes is not None else None), data_referencia=ref),
        kpis=kpis,
        vida_util=VidaUtil(itens=_int(total["lotes_com_validade"]) if total is not None else None,
                           media=_get(estado, "d7_vida_util_media"), mediana=_get(total, "mediana"),
                           p25=_get(total, "q1"), p75=_get(total, "q3"), minimo=_get(total, "minimo"),
                           maximo=_get(total, "maximo"),
                           outliers=_int(total["outliers"]) if total is not None else None,
                           mediana_mes_anterior=prev_vida),
        por_uf=_por_uf(gold.uf) if usa_foto_uf else [],
        por_categoria=_por_categoria(eventos_categoria, gold.fatos["estoque_categoria"]),
        top_abaixo_minimo=[AlimentoAbaixoMinimo(alimento=r["alimento"], categoria=r["categoria"] or SEM_CATEGORIA,
                                                households=_int(r["households"]))
                           for _, r in gold.fatos["abaixo_minimo"].iterrows()],
        tem_despensa=tem_despensa,
        parcial=(gold.ano, gold.mes) == (hoje.year, hoje.month),
        data_foto_despensa=str(estado["data_referencia"]) if estado is not None else None,
        resumo=_resumo(gold, kpis),
        evolucao=_evolucao(gold.mensal),
        desperdicio_categoria=eventos_categoria,
        desperdicio_regiao=_desperdicio_regiao(gold.fatos["evento_regiao"]),
        momento_descarte=_momento_descarte(gold.fatos["evento_momento"]),
    )


# ---------------------------------------------------------------- dashboard do site
def _monthly_waste(mensal: pd.DataFrame) -> list[dict]:
    rows = mensal.dropna(subset=["d1_pct"]).tail(12)
    out = []
    for _, r in rows.iterrows():
        month = int(str(r["ano_mes"]).split("-")[1])
        out.append({"id": str(r["ano_mes"]), "month": MONTHS_SHORT[month - 1], "rate": _num(r["d1_pct"])})
    return out


def _state_waste(uf: pd.DataFrame) -> tuple[list[dict], set[str]]:
    visible = uf[(uf["lotes"] >= MIN_LOTES_UF) & uf["d1_pct"].notna()].copy()
    visible["uf"] = visible["uf"].str.strip().str.upper()
    visible = visible[visible["uf"].isin(UF_NAME)]
    levels = quartile_levels(visible["d1_pct"].astype(float).tolist())
    states = [{"id": r["uf"], "name": UF_NAME[r["uf"]], "level": LEVELS[q]}
              for (_, r), q in zip(visible.iterrows(), levels, strict=True)]
    regions = {_region(r["regiao"], r["uf"]) for _, r in visible.iterrows()}
    return sorted(states, key=lambda s: s["id"]), regions


def _category_by_region(df: pd.DataFrame, column: str, top: int) -> tuple[list[dict], list[str]]:
    """Células (região x categoria) das `top` categorias com mais unidades em `column`, + nomes das categorias."""
    known = _known(df)
    region = known["regiao"].map(lambda r: _region(r, ""))
    known = known.assign(region=region)
    known = known[known["region"].notna()]
    categories = known.groupby("categoria")[column].sum().sort_values(ascending=False)
    categories = categories[categories > 0].head(top).index.tolist()
    totals = known[known["categoria"].isin(categories)].groupby(["categoria", "region"])[column].sum()
    regions = [rid for rid, _, _ in REGIONS if rid in set(known["region"])]
    cells = [{"id": f"{rid}-{slug(cat)}", "regionId": rid, "categoryId": slug(cat),
              "value": max(_int(totals.get((cat, rid), 0)) or 0, 0)} for rid in regions for cat in categories]
    return cells, categories


def _shelf_life_distribution(faixas: pd.DataFrame) -> list[dict]:
    if faixas.empty:
        return []  # mês sem foto da despensa: o front mostra "sem dados" em vez de barras zeradas
    counts = dict(zip(faixas["faixa"], faixas["itens"], strict=True))
    return [{"id": fid, "label": label, "count": _int(counts.get(fid, 0)) or 0}
            for _, _, fid, label in SHELF_LIFE_BUCKETS]


def _category_shelf_life(estoque: pd.DataFrame) -> list[tuple[dict, str]]:
    rows = _known(estoque).dropna(subset=["q1", "mediana", "q3", "minimo", "maximo"])
    rows = rows.sort_values("lotes", ascending=False).head(TOP_CATEGORIES)
    return [({"id": slug(r["categoria"]), "categoryId": slug(r["categoria"]), "minimum": max(_num(r["minimo"]), 0),
              "firstQuartile": _num(r["q1"]), "median": _num(r["mediana"]), "thirdQuartile": _num(r["q3"]),
              "maximum": _num(r["maximo"])}, r["categoria"]) for _, r in rows.iterrows()]


def gold_dashboard(gold: GoldData) -> dict:
    """JSON do Dashboard (DashboardData do NexUs-Web) a partir da Gold."""
    mes = _row(gold.mensal, ano_mes=ano_mes(gold.ano, gold.mes))
    estado = None if gold.estado.empty else gold.estado.iloc[0]
    expired = soon = no_expiry = 0
    if estado is not None and not pd.isna(estado["unidades"]):
        unidades = float(estado["unidades"])
        d3, d4, d8 = (float(estado[c] or 0) for c in ("d3_vencidos_pct", "d4_vencem_7d_pct", "d8_sem_validade_pct"))
        com_validade = unidades * (1 - d8 / 100)
        expired, soon, no_expiry = (round(com_validade * d3 / 100), round(com_validade * d4 / 100),
                                    round(unidades * d8 / 100))
    states, regions = _state_waste(gold.uf) if _foto_do_mes(gold) else ([], set())
    fatos = gold.fatos
    waste = _category_by_region(fatos["regiao_categoria"], "descartadas", TOP_WASTE_CATEGORIES)
    consumption = _category_by_region(fatos["regiao_categoria"], "consumidas", TOP_CATEGORIES)
    shelf = _category_shelf_life(fatos["estoque_categoria"])
    regions |= {cell["regionId"] for cell in [*waste[0], *consumption[0]]}
    names = dict.fromkeys([*waste[1], *consumption[1], *(name for _, name in shelf)])
    return {
        "summary": {"wasteRate": _get(mes, "d1_pct") or 0, "expiredKg": expired, "expiringInSevenDaysKg": soon,
                    "withoutExpiryKg": no_expiry},
        "monthlyTarget": 15.0,
        "monthlyWaste": _monthly_waste(gold.mensal),
        "stateWaste": states,
        "regions": [{"id": rid, "name": name, "abbreviation": abbr} for rid, name, abbr in REGIONS if rid in regions],
        "categories": [{"id": slug(name), "name": name} for name in names],
        "regionalWaste": [{**cell, "volume": cell.pop("value")} for cell in waste[0]],
        "regionalConsumption": [{**cell, "kilograms": cell.pop("value")} for cell in consumption[0]],
        "shelfLifeDistribution": _shelf_life_distribution(fatos["vida_util_faixas"]),
        "categoryShelfLife": [box for box, _ in shelf],
        "belowMinimum": [{"id": slug(r["alimento"]), "name": r["alimento"],
                          "missingVolume": max(_int(r["faltam"]) or 0, 0)}
                         for _, r in fatos["abaixo_minimo"].iterrows()],
        "meta": {"ano": gold.ano, "mes": gold.mes, "fonte": "databricks", "unidade": "unidades",
                 "temDespensa": estado is not None,
                 "parcial": (gold.ano, gold.mes) == (datetime.now(BRAZIL_TZ).year, datetime.now(BRAZIL_TZ).month),
                 "dataReferencia": str(estado["data_referencia"]) if estado is not None else gold.data_foto},
    }
