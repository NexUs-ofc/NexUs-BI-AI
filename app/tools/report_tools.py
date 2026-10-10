"""Report tools used by the Analyst and Recommender agents (LangChain tool calling).

- search_reports_by_period: the user named a month, year or date range.
- get_latest_reports: no period given -> use the most recent reports.

The company is NOT a tool parameter on purpose: it comes from the request context, so the LLM
can never read another company's reports.
"""
import json

from langchain_core.tools import StructuredTool

from app.config import REPORTS_LATEST_LIMIT, REPORTS_MAX_CHARS, REPORTS_MAX_MONTHS
from app.prompts.tools import (
    GET_LATEST_REPORTS_DESCRIPTION,
    INVALID_PERIOD,
    NO_REPORTS_FOUND,
    SEARCH_REPORTS_BY_PERIOD_DESCRIPTION,
)
from app.repository.report_repository import find_latest_reports, find_reports_by_period


def _to_json(reports: list[dict]) -> str:
    text = json.dumps(reports, ensure_ascii=False, default=str)
    if len(text) > REPORTS_MAX_CHARS:
        text = text[:REPORTS_MAX_CHARS] + " ...[truncado: relatórios grandes demais, peça um período menor]"
    return text


def _months_between(start_year: int, start_month: int, end_year: int, end_month: int) -> int:
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


def build_report_tools(company_id: str | None = None) -> list[StructuredTool]:
    """Create the report tools bound to one company (or to all, if company_id is None)."""

    def search_reports_by_period(
        start_month: int, start_year: int, end_month: int | None = None, end_year: int | None = None
    ) -> str:
        end_month = end_month or start_month
        end_year = end_year or start_year
        for month in (start_month, end_month):
            if not 1 <= month <= 12:
                return INVALID_PERIOD.format(reason=f"mês {month} fora de 1 a 12.")
        size = _months_between(start_year, start_month, end_year, end_month)
        if size < 1:
            return INVALID_PERIOD.format(reason="a data inicial é depois da data final.")
        if size > REPORTS_MAX_MONTHS:
            return INVALID_PERIOD.format(reason=f"o período tem {size} meses; o máximo é {REPORTS_MAX_MONTHS}.")

        reports = find_reports_by_period(start_year, start_month, end_year, end_month, company_id)
        if not reports:
            if size == 1:
                scope = f"{start_month:02d}/{start_year}"
            else:
                scope = f"{start_month:02d}/{start_year} a {end_month:02d}/{end_year}"
            return NO_REPORTS_FOUND.format(scope=scope)
        return _to_json(reports)

    def get_latest_reports(limit: int = REPORTS_LATEST_LIMIT) -> str:
        limit = max(1, min(int(limit), 12))
        reports = find_latest_reports(limit, company_id)
        if not reports:
            return NO_REPORTS_FOUND.format(scope="nenhum período (a base de relatórios está vazia)")
        return _to_json(reports)

    return [
        StructuredTool.from_function(
            search_reports_by_period,
            name="search_reports_by_period",
            description=SEARCH_REPORTS_BY_PERIOD_DESCRIPTION,
        ),
        StructuredTool.from_function(
            get_latest_reports,
            name="get_latest_reports",
            description=GET_LATEST_REPORTS_DESCRIPTION,
        ),
    ]
