"""HTML -> PDF com Playwright (Chromium headless).

Usa o Chromium do Playwright (python -m playwright install chromium). Se ele não estiver instalado (download
bloqueado pela rede, por exemplo), usa o Microsoft Edge ou o Google Chrome da máquina, que geram o mesmo PDF.
Para forçar um deles: REPORT_PDF_BROWSER=msedge (ou chrome) no .env.
"""
import logging
import os

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from report_generator.agents.narrative import period_name

FOOTER = """<div style="width:100%;font:7.5pt Arial,sans-serif;color:#6b6478;padding:0 16mm;
display:flex;justify-content:space-between"><span>NexUs BI · Relatório de {periodo}</span>
<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>"""


log = logging.getLogger("report_generator")


def _launch(p):
    """Abre o primeiro navegador disponível: o escolhido no .env, o Chromium do Playwright, Edge ou Chrome."""
    preferred = (os.getenv("REPORT_PDF_BROWSER") or "").strip()
    channels = [preferred] if preferred else [None, "msedge", "chrome"]
    errors = []
    for channel in channels:
        try:
            return p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        except PlaywrightError as error:
            errors.append(f"{channel or 'chromium do playwright'}: {str(error).splitlines()[0]}")
            log.info("Navegador indisponível (%s), tentando o próximo", channel or "chromium do playwright")
    raise RuntimeError("Nenhum navegador para gerar o PDF. Rode 'python -m playwright install chromium' ou "
                       "instale o Edge/Chrome.\n" + "\n".join(errors))


def html_to_pdf(html: str, ano: int, mes: int) -> bytes:
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            return page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=FOOTER.format(periodo=period_name(ano, mes)),
            )
        finally:
            browser.close()
