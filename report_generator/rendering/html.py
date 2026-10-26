"""JSON do relatório -> HTML (template Jinja2 fixo; a IA não escreve HTML).

O mesmo HTML serve de prévia na interface web (GET /reports/{ano}/{mes}/html) e de base para o PDF.
"""
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from report_generator.agents.narrative import period_name
from report_generator.config import BRAZIL_TZ, MIN_HOUSEHOLDS
from report_generator.formatting import br, integer, pct, pp
from report_generator.kpis import CARD_KPIS, KPIS

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


def render_html(report: dict) -> str:
    ref = report["dados"]["base"]["data_referencia"]
    return _env.get_template("relatorio.html").render(
        r=report,
        periodo=period_name(report["ano"], report["mes"]),
        data_ref="/".join(reversed(ref.split("-"))),
        gerado_em=_date_br(report["gerado_em"]),
        card_kpis=CARD_KPIS,
        kpi_defs=KPIS,
        kpi_names={k: v.nome for k, v in KPIS.items()},
        status_label=STATUS_LABEL,
        min_households=MIN_HOUSEHOLDS,
    )
