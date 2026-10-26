"""HTML -> PDF com Playwright (Chromium headless).

Instalação (uma vez por máquina):  pip install playwright  e  python -m playwright install chromium
"""
from playwright.sync_api import sync_playwright

from report_generator.agents.narrative import period_name

FOOTER = """<div style="width:100%;font:7.5pt Arial,sans-serif;color:#5d6773;padding:0 16mm;
display:flex;justify-content:space-between"><span>NexUs BI · Relatório de {periodo}</span>
<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>"""


def html_to_pdf(html: str, ano: int, mes: int) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch()
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
