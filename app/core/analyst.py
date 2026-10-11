"""Descriptive Analyst agent: describes what the consolidated reports show (create_agent + report tools)."""
from datetime import date

from app.core.base import build_agent, final_text, run_agent, tool_trace
from app.prompts.analyst import ANALYST_PROMPT
from app.prompts.tools import NO_TOOL_CALLED
from app.schemas.agents import SpecialistAnswer
from app.tools.report_tools import build_report_tools


def analyst_agent(question: str, history: list) -> SpecialistAnswer:
    prompt = ANALYST_PROMPT.format(today=date.today().strftime("%d/%m/%Y"))
    tools = build_report_tools()
    state = run_agent(build_agent(prompt, tools), question, history)
    calls, log = tool_trace(state, tools)
    return SpecialistAnswer(answer=final_text(state), context="\n\n".join(log) or NO_TOOL_CALLED, tool_calls=calls)
