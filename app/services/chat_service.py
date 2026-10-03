"""Chat service: the bridge between the controller (HTTP) and the Orchestrator (agents)."""
import uuid

from app.core.memory import clear_session, store
from app.core.orchestrator import Orchestrator
from app.model.llm import explain_error
from app.schemas.api import ChatRequest, ChatResponse


class LLMError(Exception):
    """Failure talking to the model (quota, key, unavailability...)."""


def answer_question(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = Orchestrator(session_id).process(request.question)
    except Exception as e:  # noqa: BLE001
        raise LLMError(explain_error(e)) from e

    return ChatResponse(
        session_id=session_id,
        answer=result.answer,
        route=result.route,
        steps=result.steps if request.debug else None,
    )


def end_session(session_id: str) -> bool:
    """Erase the session memory. Returns False if it did not exist."""
    existed = session_id in store
    clear_session(session_id)
    return existed
