"""Recommender agent: perceptions and insights. It does NOT make decisions."""
from app.core.base import build_chain
from app.prompts.analyst import NO_DATA
from app.prompts.recommender import RECOMMENDER_PROMPT
from app.schemas.agents import SpecialistAnswer


def recommender_agent(question: str, history: list, data: str = "") -> SpecialistAnswer:
    # `data` will come from the database tools once they are defined (see core/orchestrator.py)
    context = data or NO_DATA
    answer = build_chain(RECOMMENDER_PROMPT).invoke({"question": question, "history": history, "context": context})
    return SpecialistAnswer(answer=answer, context=data)
