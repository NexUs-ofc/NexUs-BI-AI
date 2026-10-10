"""Recommender agent: perceptions and insights from the reports. It does NOT make decisions."""
from datetime import date

from app.core.base import run_with_tools
from app.prompts.recommender import NO_TOOL_CALLED, RECOMMENDER_PROMPT
from app.schemas.agents import SpecialistAnswer
from app.tools.report_tools import build_report_tools


def recommender_agent(question: str, history: list, company_id: str | None = None) -> SpecialistAnswer:
    answer, tool_log, tool_calls = run_with_tools(
        RECOMMENDER_PROMPT, question, history, build_report_tools(company_id), today=date.today().strftime("%d/%m/%Y")
    )
    return SpecialistAnswer(answer=answer, context="\n\n".join(tool_log) or NO_TOOL_CALLED, tool_calls=tool_calls)
