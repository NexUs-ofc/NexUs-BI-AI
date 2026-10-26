"""Geração do relatório de um mês, de ponta a ponta.

1. carrega os dados do mês (mock ou base)          data/loader.py
2. lê o histórico (JSONs anteriores no Mongo)       storage/mongo.py
3. calcula os números (análise descritiva)          analysis/descriptive.py
4. agentes escrevem a narrativa (ou regras --sem-ia) agents/
5. checa os números da narrativa                    agents/quality.py
6. salva o JSON no Mongo (status = rascunho)
7. JSON -> HTML -> PDF -> GCS, e grava a URI do PDF no JSON
"""
import logging
from datetime import datetime, timezone

from report_generator.agents.fallback import build_fallback_narrative
from report_generator.agents.narrative import generate_narrative, period_name
from report_generator.agents.quality import known_numbers, unsupported_numbers
from report_generator.analysis.descriptive import build_dados
from report_generator.config import HISTORY_MONTHS
from report_generator.data.loader import load_month
from report_generator.rendering.html import render_html
from report_generator.schemas import Relatorio
from report_generator.storage import files, mongo

log = logging.getLogger("report_generator")


def build_report(ano: int, mes: int, use_ai: bool = True, model=None) -> dict:
    """Passos 1 a 5: devolve o documento (dict pronto para o Mongo), sem salvar nada."""
    log.info("Carregando dados de %02d/%d", mes, ano)
    month = load_month(ano, mes)
    history = mongo.find_previous_dados(ano, mes, HISTORY_MONTHS)
    previous = history[0]["dados"] if history and _is_previous_month(history[0], ano, mes) else None

    log.info("Calculando KPIs (%d meses de histórico)", len(history))
    dados = build_dados(month, previous)

    if use_ai:
        log.info("Gerando narrativa com os agentes")
        result = generate_narrative(dados, history, ano, mes, model=model)
        narrativa, tool_out = result.narrativa, result.tool_outputs
    else:
        narrativa, tool_out = build_fallback_narrative(dados, history, period_name(ano, mes)), []

    dados_dict = dados.model_dump()
    known = known_numbers(dados_dict, [h["dados"] for h in history], *tool_out)
    missing = unsupported_numbers(narrativa.model_dump(), known)
    if missing:
        log.warning("Números na narrativa sem fonte nos dados: %s", missing)

    report = Relatorio(
        ano=ano, mes=mes, fonte_dados=month.fonte, gerado_em=datetime.now(timezone.utc), gerado_com_ia=use_ai,
        dados=dados, narrativa=narrativa,
        qualidade={"numeros_sem_fonte": missing, "meses_de_historico": len(history)},
    )
    return report.model_dump(mode="json")


def _is_previous_month(h: dict, ano: int, mes: int) -> bool:
    prev = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return (h["ano"], h["mes"]) == prev


def render_pdf(report: dict) -> bytes:
    # Import aqui dentro: o Playwright só é carregado quando for gerar PDF
    from report_generator.rendering.pdf import html_to_pdf

    return html_to_pdf(render_html(report), report["ano"], report["mes"])


def run(ano: int, mes: int, use_ai: bool = True, with_pdf: bool = True, model=None) -> dict:
    """Pipeline completo (passos 1 a 7). Usado pela CLI e pela API."""
    if not 1 <= mes <= 12:
        raise ValueError(f"Mês inválido: {mes}")
    report = build_report(ano, mes, use_ai=use_ai, model=model)
    mongo.save_report(report)
    log.info("JSON salvo no MongoDB (%02d/%d, rascunho)", mes, ano)
    if with_pdf:
        uri = files.save_pdf(render_pdf(report), ano, mes)
        mongo.set_pdf(ano, mes, uri)
        report["pdf"] = {"uri": uri}
        log.info("PDF salvo em %s", uri)
    return report
