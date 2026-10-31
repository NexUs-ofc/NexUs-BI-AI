"""JSON do Dashboard do site (GET /dashboard) a partir do MOCK. Com a Gold, veja analysis/gold.py.

O formato é o `DashboardData` do front-end (NexUs-Web: src/types/dashboard.ts), validado lá por
src/utils/validateDashboard.ts: camelCase, ids únicos e números >= 0 (nunca null). Por isso valores
suprimidos por privacidade são OMITIDOS, não enviados como null.

Parte dos mesmos números do relatório (build_dados) e acrescenta os recortes que só a tela usa: região,
heatmap categoria x região, histograma e boxplot de vida útil. A base não guarda peso: os campos
"Kg"/"volume"/"kilograms" do contrato levam CONTAGEM de itens (cards) ou de eventos (região).

    summary                 -> 4 cards do topo
    monthlyWaste + target   -> linha "taxa de desperdício por mês x meta" (histórico do Mongo + mês atual)
    stateWaste              -> mapa por UF (highest / intermediate / average / lowest, por quartil)
    regionalWaste           -> barras empilhadas: itens vencidos por categoria em cada região
    regionalConsumption     -> heatmap: itens consumidos por categoria x região
    shelfLifeDistribution   -> histograma de vida útil
    categoryShelfLife       -> boxplot de vida útil por categoria
    belowMinimum            -> top 10 alimentos abaixo do mínimo (households)
"""
import re
import unicodedata

import pandas as pd

from report_generator.analysis.descriptive import build_dados, with_expiry_flags
from report_generator.config import MIN_HOUSEHOLDS
from report_generator.data.loader import MonthData

REGIONS = [("norte", "Norte", "N"), ("nordeste", "Nordeste", "NE"), ("centro-oeste", "Centro-Oeste", "CO"),
           ("sudeste", "Sudeste", "SE"), ("sul", "Sul", "S")]
UF_REGION = {
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "nordeste"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "centro-oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "sul"),
}
UF_NAME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
LEVELS = ["lowest", "average", "intermediate", "highest"]  # quartil 1 -> 4 (claro -> escuro no mapa)
MONTHS_SHORT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
SHELF_LIFE_BUCKETS = [(0, 7, "0-7", "0–7"), (8, 14, "8-14", "8–14"), (15, 21, "15-21", "15–21"),
                      (22, 28, "22-28", "22–28"), (29, 35, "29-35", "29–35"), (36, None, "36-mais", "36+")]
MAX_MONTHS = 12
TOP_WASTE_CATEGORIES = 3  # barras empilhadas
TOP_CATEGORIES = 5  # heatmap e boxplot


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _number(value) -> float:
    return round(float(value), 1)


def quartile_levels(values: list[float]) -> list[int]:
    """Índice em LEVELS (0 = mais baixo ... 3 = mais alto) de cada valor, por quartil."""
    if not values:
        return []
    ranks = pd.Series(values).rank(method="dense", pct=True)
    return ranks.mul(4).sub(1e-9).astype(int).clip(0, 3).tolist()


def _visible_regions(households: pd.DataFrame) -> list[str]:
    """Regiões com households suficientes para mostrar números (mesma regra de privacidade das UFs)."""
    region = households["uf"].map(UF_REGION)
    count = households.assign(region=region).groupby("region")["household_id"].nunique()
    return [rid for rid, _, _ in REGIONS if count.get(rid, 0) >= MIN_HOUSEHOLDS]


def _state_waste(dados) -> list[dict]:
    rows = [u for u in dados.por_uf if not u.suprimido and u.d3_pct_vencidos is not None and u.uf in UF_NAME]
    if not rows:
        return []
    levels = quartile_levels([u.d3_pct_vencidos for u in rows])
    return [{"id": u.uf, "name": UF_NAME[u.uf], "level": LEVELS[q]}
            for u, q in sorted(zip(rows, levels, strict=True), key=lambda x: x[0].uf)]


def _category_by_region(events: pd.DataFrame, event_type: str, regions: list[str], top: int) -> pd.Series:
    """Contagem de eventos por (categoria, região), só das `top` categorias com mais eventos."""
    ev = events[events["event_type"] == event_type].assign(region=lambda d: d["uf"].map(UF_REGION))
    ev = ev[ev["region"].isin(regions)]
    categories = ev["categoria"].value_counts().head(top).index
    return ev[ev["categoria"].isin(categories)].groupby(["categoria", "region"]).size()


def _cells(counts: pd.Series, regions: list[str], field: str) -> list[dict]:
    categories = list(dict.fromkeys(counts.index.get_level_values(0)))
    return [{"id": f"{rid}-{slug(cat)}", "regionId": rid, "categoryId": slug(cat), field: int(counts.get((cat, rid), 0))}
            for rid in regions for cat in categories]


def _shelf_life_distribution(days: pd.Series) -> list[dict]:
    out = []
    for lo, hi, bucket_id, label in SHELF_LIFE_BUCKETS:
        mask = days >= lo if hi is None else days.between(lo, hi)
        out.append({"id": bucket_id, "label": label, "count": int(mask.sum())})
    return out


def _category_shelf_life(items: pd.DataFrame) -> tuple[list[dict], list[str]]:
    valid = items[items["tem_validade"]].dropna(subset=["vida_util_dias"])
    valid = valid[valid["vida_util_dias"] >= 0]
    out, names = [], []
    for cat in valid["categoria"].value_counts().head(TOP_CATEGORIES).index:
        days = valid.loc[valid["categoria"] == cat, "vida_util_dias"]
        q1, q3 = days.quantile(0.25), days.quantile(0.75)
        iqr = q3 - q1
        inside = days[(days >= q1 - 1.5 * iqr) & (days <= q3 + 1.5 * iqr)]  # bigodes sem outliers
        out.append({"id": slug(cat), "categoryId": slug(cat), "minimum": _number(inside.min()),
                    "firstQuartile": _number(q1), "median": _number(days.median()), "thirdQuartile": _number(q3),
                    "maximum": _number(inside.max())})
        names.append(cat)
    return out, names


def _monthly_waste(history: list[dict], ano: int, mes: int, current: float | None) -> list[dict]:
    points = [(h["ano"], h["mes"], ((h.get("dados") or {}).get("kpis", {}).get("D1") or {}).get("valor"))
              for h in reversed(history)]  # history vem do mais recente para o mais antigo
    points.append((ano, mes, current))
    return [{"id": f"{a}-{m:02d}", "month": MONTHS_SHORT[m - 1], "rate": v}
            for a, m, v in points[-MAX_MONTHS:] if v is not None]


def build_dashboard(month: MonthData, history: list[dict] | None = None) -> dict:
    """`history`: meses anteriores ({ano, mes, dados}, do mais recente para o mais antigo), do Mongo."""
    history = history or []
    dados = build_dados(month, history[0]["dados"] if history else None)
    items = with_expiry_flags(month)
    valid = items[items["tem_validade"]]
    regions = _visible_regions(month.households)

    waste = _category_by_region(month.events, "item_expired", regions, TOP_WASTE_CATEGORIES)
    consumption = _category_by_region(month.events, "item_consumed", regions, TOP_CATEGORIES)
    shelf_life, shelf_names = _category_shelf_life(items)
    category_names = dict.fromkeys([*waste.index.get_level_values(0), *consumption.index.get_level_values(0),
                                    *shelf_names])
    d1 = dados.kpis["D1"]

    return {
        "summary": {
            "wasteRate": d1.valor or 0,
            "expiredKg": int(valid["vencido"].sum()),
            "expiringInSevenDaysKg": int(valid["a_vencer_7d"].sum()),
            "withoutExpiryKg": int((~items["tem_validade"]).sum()),
        },
        "monthlyTarget": d1.meta,
        "monthlyWaste": _monthly_waste(history, month.ano, month.mes, d1.valor),
        "stateWaste": _state_waste(dados),
        "regions": [{"id": rid, "name": name, "abbreviation": abbr} for rid, name, abbr in REGIONS if rid in regions],
        "categories": [{"id": slug(c), "name": c} for c in category_names],
        "regionalWaste": _cells(waste, regions, "volume"),
        "regionalConsumption": _cells(consumption, regions, "kilograms"),
        "shelfLifeDistribution": _shelf_life_distribution(valid["vida_util_dias"].dropna()),
        "categoryShelfLife": shelf_life,
        "belowMinimum": [{"id": slug(r.alimento), "name": r.alimento, "missingVolume": r.households}
                         for r in dados.top_abaixo_minimo],
        # Fora do contrato do front (ele ignora campos extras): de onde e de quando vêm os números
        "meta": {"ano": month.ano, "mes": month.mes, "fonte": month.fonte, "unidade": "itens",
                 "dataReferencia": month.data_referencia.isoformat()},
    }
