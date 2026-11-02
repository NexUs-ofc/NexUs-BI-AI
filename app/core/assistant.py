"""The NexUs BI assistant: one agent with the FAQ tool (Qdrant) and the report tools (MongoDB).

It replaces the old router + FAQ/Analyst/Recommender agents: choosing which source to read is exactly
what tool calling does, so routing with an extra Gemini call only added latency.
The route returned to the front-end and saved in the metrics comes from the tools the agent used.
"""
from app.config import today_in_brazil
from app.core.base import build_agent, final_text, run_agent, tool_trace
from app.core.prompts.assistant import ASSISTANT_PROMPT, RECOMMENDER_DISCLAIMER
from app.schemas.agents import SpecialistAnswer
from app.tools.faq_tools import build_faq_tools
from app.tools.report_tools import build_report_tools

REPORT_TOOLS = {"search_reports_by_period", "get_latest_reports"}


def _route(tool_calls: list[str]) -> str:
    """analyst = read reports; faq = searched the FAQ or answered without data (greeting, BI concept...)."""
    names = {call.split("(", 1)[0] for call in tool_calls}
    return "analyst" if names & REPORT_TOOLS else "faq"


def assistant_agent(question: str, history: list, config: dict | None = None) -> SpecialistAnswer:
    prompt = ASSISTANT_PROMPT.format(today=today_in_brazil().strftime("%d/%m/%Y"), disclaimer=RECOMMENDER_DISCLAIMER)
    tools = build_faq_tools() + build_report_tools()
    state = run_agent(build_agent(prompt, tools), question, history, config)
    calls, log = tool_trace(state, tools)
    return SpecialistAnswer(answer=final_text(state), context="\n\n".join(log), tool_calls=calls, route=_route(calls))
