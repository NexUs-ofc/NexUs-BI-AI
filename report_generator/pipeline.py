"""Geração do relatório de um mês, de ponta a ponta.

1. lê o histórico (JSONs anteriores no Mongo)       storage/mongo.py
2-3. KPIs do mês: Gold do Databricks ou mock        data/loader.py (analysis/gold.py ou descriptive.py)
4. agentes escrevem a narrativa (ou regras --sem-ia) agents/
5. checa os números da narrativa                    agents/quality.py
6. salva o JSON no Mongo (status = rascunho)
7. JSON -> HTML (com gráficos) -> PDF -> Supabase Storage, e grava a URI do PDF no JSON
"""
import logging
from datetime import UTC, datetime

from report_generator.agents.fallback import build_fallback_narrative
from report_generator.agents.narrative import generate_narrative, period_name
from report_generator.agents.quality import known_numbers, unsupported_numbers
from report_generator.analysis.acoes import acoes_app
from report_generator.analysis.textos import narrativa_sem_codigos
from report_generator.config import BRAZIL_TZ, HISTORY_MONTHS
from report_generator.data.loader import load_dados
from report_generator.rendering.html import render_html
from report_generator.schemas import Narrativa, Relatorio
from report_generator.storage import files, mongo

log = logging.getLogger("report_generator")


def build_report(ano: int, mes: int, use_ai: bool = True, model=None) -> dict:
    """Passos 1 a 5: devolve o documento (dict pronto para o Mongo), sem salvar nada."""
    history = mongo.find_previous_dados(ano, mes, HISTORY_MONTHS)
    previous = history[0]["dados"] if history and _is_previous_month(history[0], ano, mes) else None

    log.info("Carregando os KPIs de %02d/%d (%d meses de histórico)", mes, ano, len(history))
    dados, fonte = load_dados(ano, mes, previous)

    if use_ai:
        log.info("Gerando narrativa com os agentes")
        result = generate_narrative(dados, history, ano, mes, model=model)
        narrativa, tool_out = result.narrativa, result.tool_outputs
    else:
        narrativa, tool_out = build_fallback_narrative(dados, history, period_name(ano, mes)), []

    narrativa = Narrativa(**narrativa_sem_codigos(narrativa.model_dump()))  # o leitor não conhece "D1", "D2"...
    dados.parcial = is_current_month(ano, mes)

    dados_dict = dados.model_dump()
    known = known_numbers(dados_dict, [h["dados"] for h in history], *tool_out)
    missing = unsupported_numbers(narrativa.model_dump(), known)
    if missing:
        log.warning("Números na narrativa sem fonte nos dados: %s", missing)

    qualidade = {"numeros_sem_fonte": missing, "meses_de_historico": len(history),
                 "sem_foto_da_despensa": not dados.tem_despensa}
    if fonte == "databricks" and dados.tem_despensa and not dados.por_uf:
        # kpi_uf só tem a foto de hoje: num mês que não é o da foto, fica vazio de propósito
        # (analysis/gold.py:_foto_do_mes) em vez de mostrar dados de hoje com rótulo errado.
        qualidade["uf_fora_do_mes"] = True

    report = Relatorio(
        ano=ano, mes=mes, fonte_dados=fonte, gerado_em=datetime.now(UTC), gerado_com_ia=use_ai,
        dados=dados, narrativa=narrativa, acoes_app=acoes_app(dados), parcial=dados.parcial,
        qualidade=qualidade,
    )
    return report.model_dump(mode="json")


def is_current_month(ano: int, mes: int) -> bool:
    now = datetime.now(BRAZIL_TZ)
    return (ano, mes) == (now.year, now.month)


def _is_previous_month(h: dict, ano: int, mes: int) -> bool:
    prev = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return (h["ano"], h["mes"]) == prev


def load_history(ano: int, mes: int) -> list[dict]:
    """Meses anteriores (só `dados`), para o gráfico de evolução do relatório."""
    return mongo.find_previous_dados(ano, mes, HISTORY_MONTHS)


def render_pdf(report: dict) -> bytes:
    # Import aqui dentro: o Playwright só é carregado quando for gerar PDF
    from report_generator.rendering.pdf import html_to_pdf

    html = render_html(report, load_history(report["ano"], report["mes"]))
    return html_to_pdf(html, report["ano"], report["mes"])


def run(ano: int, mes: int, use_ai: bool = True, with_pdf: bool = True, model=None,
        keep_status: bool = True) -> dict:
    """Pipeline completo (passos 1 a 7). Usado pela CLI e pela API.

    `keep_status`: gerar de novo um mês que já está PUBLICADO mantém "publicado" e o PDF atual (o relatório
    diário do mês em andamento não some do site nem do chatbot a cada atualização). Com False, volta a rascunho."""
    if not 1 <= mes <= 12:
        raise ValueError(f"Mês inválido: {mes}")
    report = build_report(ano, mes, use_ai=use_ai, model=model)
    existing = mongo.find_report(ano, mes) if keep_status else None
    if existing:
        if existing.get("status") == "publicado":
            report["status"] = "publicado"
        if existing.get("pdf"):
            report["pdf"] = existing["pdf"]
    mongo.save_report(report)
    log.info("JSON salvo no MongoDB (%02d/%d, rascunho)", mes, ano)
    if with_pdf:
        uri = files.save_pdf(render_pdf(report), ano, mes)
        mongo.set_pdf(ano, mes, uri)
        report["pdf"] = {"uri": uri}
        log.info("PDF salvo em %s", uri)
    return report
