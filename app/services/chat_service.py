"""Chat service: the bridge between the controller (HTTP) and the Orchestrator (agents)."""
import uuid

from app.core.memory import clear_session, store
from app.core.orchestrator import Orchestrator
from app.model.llm import explain_error
from app.schemas.api import ChatRequest, ChatResponse, CurrentUser


class LLMError(Exception):
    """Failure talking to the model (quota, key, unavailability...)."""


def _memory_key(session_id: str, user: CurrentUser) -> str:
    """The memory is stored per company + session: another company that guesses (or reuses)
    the session_id still gets an empty history."""
    return f"{user.company_id}:{session_id}"


def answer_question(request: ChatRequest, user: CurrentUser) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = Orchestrator(_memory_key(session_id, user)).process(request.question)
    except Exception as e:
        raise LLMError(explain_error(e)) from e

    return ChatResponse(
        session_id=session_id,
        answer=result.answer,
        route=result.route,
        steps=result.steps if request.debug else None,
    )


def end_session(session_id: str, user: CurrentUser) -> bool:
    """Erase the session memory. Returns False if it did not exist."""
    key = _memory_key(session_id, user)
    existed = key in store
    clear_session(key)
    return existed
