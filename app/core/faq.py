"""FAQ agent: answers general questions, searching the FAQ (Qdrant) through the search_faq tool."""
from app.core.base import build_agent, final_text, run_agent, tool_trace
from app.prompts.faq import FAQ_PROMPT
from app.prompts.tools import FAQ_NOT_SEARCHED
from app.schemas.agents import SpecialistAnswer
from app.tools.faq_tools import build_faq_tools


def faq_agent(question: str, history: list) -> SpecialistAnswer:
    tools = build_faq_tools()
    state = run_agent(build_agent(FAQ_PROMPT, tools), question, history)
    calls, log = tool_trace(state, tools)
    return SpecialistAnswer(answer=final_text(state), context="\n\n".join(log) or FAQ_NOT_SEARCHED, tool_calls=calls)
