"""Report tools (LangChain tool calling): real reads of the monthly reports in MongoDB.

- search_reports_by_period: the user named a month, year or date range.
- get_latest_reports: no period given -> use the most recent reports.

Business rule of the MVP: the reports are the same for every company, so the tools do not filter by
company. Authentication (auth/dependencies.py) already guarantees who the caller is.

If MongoDB fails the tool raises ExternalServiceError (the chat answers with a clear error). What goes to
the model is capped by REPORTS_MAX_CHARS: whole reports are dropped from the oldest one, never cut in the
middle of the JSON.
"""
import json

from langchain_core.tools import StructuredTool

from app.config import REPORTS_LATEST_LIMIT, REPORTS_MAX_CHARS, REPORTS_MAX_MONTHS
from app.core.errors import ExternalServiceError
from app.core.prompts.tools import (
    GET_LATEST_REPORTS_DESCRIPTION,
    INVALID_PERIOD,
    NO_REPORTS_FOUND,
    SEARCH_REPORTS_BY_PERIOD_DESCRIPTION,
)
from app.observability import trace
from app.observability.trace import redact
from app.repository.report_repository import find_latest_reports, find_reports_by_period

TRUNCATED_NOTE = "[{dropped} relatório(s) mais antigo(s) omitido(s) por tamanho; peça um período menor]"


def _to_json(reports: list[dict], info: dict) -> str:
    """Reports newest first; drop the oldest until the text fits REPORTS_MAX_CHARS."""
    kept = list(reports)
    text = json.dumps(kept, ensure_ascii=False, default=str)
    while len(text) > REPORTS_MAX_CHARS and len(kept) > 1:
        kept.pop()
        text = json.dumps(kept, ensure_ascii=False, default=str)
    dropped = len(reports) - len(kept)
    if dropped:
        text += "\n" + TRUNCATED_NOTE.format(dropped=dropped)
    info.update(relatorios=len(reports), enviados=len(kept), chars_para_modelo=len(text))
    return text


def _months_between(start_year: int, start_month: int, end_year: int, end_month: int) -> int:
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


def _read(query, **fields) -> list[dict]:
    with trace.step("mongodb.relatorios", service="mongodb", **fields) as info:
        try:
            reports = query()
        except Exception as error:  # timeout, auth, network...
            raise ExternalServiceError("MongoDB", f"não foi possível ler os relatórios ({redact(error, 150)}).") from error
        info["documentos"] = len(reports)
    return reports


def build_report_tools() -> list[StructuredTool]:
    """Create the report tools used by the assistant."""

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

        period = f"{start_month:02d}/{start_year}-{end_month:02d}/{end_year}"
        with trace.step("tool.search_reports_by_period", periodo=period) as info:
            reports = _read(lambda: find_reports_by_period(start_year, start_month, end_year, end_month), periodo=period)
            if not reports:
                info["relatorios"] = 0
                scope = (f"{start_month:02d}/{start_year}" if size == 1
                         else f"{start_month:02d}/{start_year} a {end_month:02d}/{end_year}")
                return NO_REPORTS_FOUND.format(scope=scope)
            return _to_json(reports, info)

    def get_latest_reports(limit: int = REPORTS_LATEST_LIMIT) -> str:
        limit = max(1, min(int(limit), 12))
        with trace.step("tool.get_latest_reports", limite=limit) as info:
            reports = _read(lambda: find_latest_reports(limit), limite=limit)
            if not reports:
                info["relatorios"] = 0
                return NO_REPORTS_FOUND.format(scope="nenhum período (a base de relatórios está vazia)")
            return _to_json(reports, info)

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
