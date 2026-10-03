"""Descriptive Analyst agent: describes what the company data shows."""
from app.core.base import build_chain
from app.prompts.analyst import ANALYST_PROMPT, NO_DATA
from app.schemas.agents import SpecialistAnswer


def analyst_agent(question: str, history: list, data: str = "") -> SpecialistAnswer:
    # `data` will come from the database tools once they are defined (see core/orchestrator.py)
    context = data or NO_DATA
    answer = build_chain(ANALYST_PROMPT).invoke({"question": question, "history": history, "context": context})
    return SpecialistAnswer(answer=answer, context=data)
