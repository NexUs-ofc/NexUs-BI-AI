"""PDF de verdade (Playwright). No CI o Chromium é instalado; onde não houver navegador, o teste é pulado."""
import pytest

from report_generator import pipeline


def test_pdf_is_generated(db):
    report = pipeline.build_report(2026, 10, use_ai=False)
    try:
        content = pipeline.render_pdf(report)
    except RuntimeError as error:
        if "Nenhum navegador" in str(error):
            pytest.skip("sem navegador para gerar PDF nesta máquina")
        raise
    assert content.startswith(b"%PDF") and len(content) > 10_000
