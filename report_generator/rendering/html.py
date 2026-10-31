"""JSON do relatório -> HTML (template Jinja2 fixo; a IA não escreve HTML).

O HTML é a base do PDF (rendering/pdf.py).
Os gráficos são SVGs gerados em rendering/charts.py a partir dos números de `dados`.
"""
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from report_generator.agents.narrative import period_name
from report_generator.config import BRAZIL_TZ, MIN_HOUSEHOLDS
from report_generator.formatting import br, integer, pct, pp
from report_generator.kpis import CARD_KPIS, EVENT_KPIS, KPIS
from report_generator.rendering import charts

TEMPLATES = Path(__file__).parent / "templates"
STATUS_LABEL = {"dentro_meta": "Dentro da meta", "acima_da_meta": "Acima da meta", "alerta": "Alerta",
                "sem_meta": "Sem meta", "sem_dados": "Sem dados"}

_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
_env.filters.update(pct=pct, pp=pp, int_br=integer, dec2=lambda v: br(v, 2))


def _date_br(value) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        return value.astimezone(BRAZIL_TZ).strftime("%d/%m/%Y %H:%M") if value.tzinfo else value.strftime(
            "%d/%m/%Y %H:%M")
    return str(value)


def _evolucao(report: dict, history: list[dict] | None) -> list[dict]:
    """Últimos meses de taxa de desperdício e descarte por esquecimento. Vem de `dados.evolucao` (Gold); em
    relatórios antigos/mock monta a partir dos `dados` dos meses anteriores no Mongo + o mês atual."""
    d = report["dados"]
    if d.get("evolucao"):
        return d["evolucao"]
    meses = [*reversed(history or []), {"ano": report["ano"], "mes": report["mes"], "dados": d}]
    return [{"ano_mes": f"{m['ano']}-{m['mes']:02d}", "d1": (m["dados"].get("kpis", {}).get("D1") or {}).get("valor"),
             "d2": (m["dados"].get("kpis", {}).get("D2") or {}).get("valor"), "completo": True}
            for m in meses[-6:]]


def _date_only(value) -> str | None:
    return None if not value else "/".join(reversed(str(value)[:10].split("-")))


def build_charts(report: dict, history: list[dict] | None = None) -> dict:
    d = report["dados"]
    tem_despensa = d.get("tem_despensa", True)
    return {
        "meters": {code: charts.kpi_meter(d["kpis"][code]) for code in CARD_KPIS
                   if code in d["kpis"] and (tem_despensa or code == "D1")},
        "evolucao": charts.evolucao_desperdicio(_evolucao(report, history), KPIS["D1"].meta),
        "cat_waste": charts.desperdicio_por_categoria(d.get("desperdicio_categoria", [])),
        "regioes": charts.desperdicio_por_regiao(d.get("desperdicio_regiao", []), KPIS["D1"].meta),
        "momento": charts.momento_do_descarte(d.get("momento_descarte", [])),
        "uf": charts.uf_vencimento(d["por_uf"]),
        "cat_d9": charts.categoria_d9(d["por_categoria"]),
        "cat_d4": charts.categoria_d4(d["por_categoria"], KPIS["D4"].meta),
        "top_min": charts.top_abaixo_minimo(d["top_abaixo_minimo"]),
        "vida": charts.vida_util_box(d["vida_util"]),
    }


def render_html(report: dict, history: list[dict] | None = None) -> str:
    """`history`: meses anteriores ({ano, mes, dados}, do mais recente para o mais antigo), para o
    gráfico de evolução. Sem histórico o gráfico de evolução não aparece."""
    dados = report["dados"]
    ref = dados["base"]["data_referencia"]
    kpis = dados["kpis"]
    tem_despensa = dados.get("tem_despensa", True)
    cards = [c for c in CARD_KPIS if c in kpis and (tem_despensa or c == "D1")]
    resumo = dados.get("resumo") or {}
    avaliados = resumo.get("avaliados") or sum(kpis[c]["valor"] is not None for c in cards)
    fora = resumo.get("fora_da_meta")
    if fora is None:
        fora = sum(kpis[c]["status"] in ("acima_da_meta", "alerta") for c in cards)
    return _env.get_template("relatorio.html").render(
        r=report,
        periodo=period_name(report["ano"], report["mes"]),
        data_ref="/".join(reversed(ref.split("-"))),
        data_ref_geral=_date_only(str(report.get("gerado_em", ""))[:10]) or "",
        gerado_em=_date_br(report["gerado_em"]),
        card_kpis=cards,
        tem_despensa=tem_despensa,
        resumo=resumo,
        avaliados=avaliados,
        fora_meta=fora,
        parcial=bool(dados.get("parcial")),
        data_foto=_date_only(dados.get("data_foto_despensa")),
        evento_codes=EVENT_KPIS,
        estado_codes=["D3", "D4", "D5", "D6", "D7", "D8"],
        kpi_defs=KPIS,
        kpi_names={k: v.nome for k, v in KPIS.items()},
        status_label=STATUS_LABEL,
        min_households=MIN_HOUSEHOLDS,
        charts=build_charts(report, history),
    )
