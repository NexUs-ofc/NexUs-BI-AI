"""Router agent: decides which specialist handles the question (create_agent with structured output)."""
from app.core.base import build_agent, run_agent, structured_output
from app.prompts.router import ROUTER_PROMPT
from app.schemas.agents import RouteDecision

FALLBACK = RouteDecision(route="faq", reason="fallback: saída do roteador fora do formato")


def route(question: str, history: list) -> RouteDecision:
    agent = build_agent(ROUTER_PROMPT, response_format=RouteDecision, temperature=0)
    # API errors (quota, key, network) bubble up so the caller can show the real message.
    state = run_agent(agent, question, history)
    return structured_output(state) or FALLBACK
