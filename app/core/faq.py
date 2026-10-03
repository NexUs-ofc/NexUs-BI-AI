"""FAQ agent: answers general questions using the FAQ indexed in Qdrant."""
from app.config import FAQ_TOP_K
from app.core.base import build_chain
from app.prompts.faq import FAQ_PROMPT, NO_FAQ
from app.repository.faq_repository import search_faq
from app.schemas.agents import SpecialistAnswer


def _format(items: list[dict]) -> str:
    return "\n\n".join(f"P: {i.get('question', '')}\nR: {i.get('answer', '')}" for i in items)


def faq_agent(question: str, history: list) -> SpecialistAnswer:
    context = _format(search_faq(question, FAQ_TOP_K)) or NO_FAQ
    answer = build_chain(FAQ_PROMPT).invoke({"question": question, "history": history, "context": context})
    return SpecialistAnswer(answer=answer, context=context)
