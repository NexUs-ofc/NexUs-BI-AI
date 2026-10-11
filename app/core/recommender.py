"""Recommender agent: perceptions and insights from the reports (create_agent + report tools).
It does NOT make decisions."""
from app.config import today_in_brazil
from app.core.base import build_agent, final_text, run_agent, tool_trace
from app.core.prompts.recommender import RECOMMENDER_PROMPT
from app.core.prompts.tools import NO_TOOL_CALLED
from app.schemas.agents import SpecialistAnswer
from app.tools.report_tools import build_report_tools


def recommender_agent(question: str, history: list) -> SpecialistAnswer:
    prompt = RECOMMENDER_PROMPT.format(today=today_in_brazil().strftime("%d/%m/%Y"))
    tools = build_report_tools()
    state = run_agent(build_agent(prompt, tools), question, history)
    calls, log = tool_trace(state, tools)
    return SpecialistAnswer(answer=final_text(state), context="\n\n".join(log) or NO_TOOL_CALLED, tool_calls=calls)
