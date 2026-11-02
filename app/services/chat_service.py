"""Chat service: the bridge between the controller (HTTP) and the Orchestrator.

Errors become ChatError with an HTTP status and a message the front-end can show as is:
- 503: a data service failed (MongoDB, Qdrant) -> never answer with made-up data
- 504: the whole message took longer than CHAT_TIMEOUT_S
- 502: the Gemini call failed (quota, key, model, network)
"""
import uuid

from app.core.errors import ExternalServiceError
from app.core.memory import clear_session, store
from app.core.orchestrator import ChatTimeoutError, Orchestrator
from app.model.llm import explain_error
from app.observability import trace
from app.schemas.api import ChatRequest, ChatResponse, CurrentUser


class ChatError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _memory_key(session_id: str, user: CurrentUser) -> str:
    """The memory is stored per company (or profile) + session: another user that guesses (or reuses)
    the session_id still gets an empty history."""
    return f"{user.company_id or user.profile_id}:{session_id}"


def _to_chat_error(error: Exception) -> ChatError:
    if isinstance(error, ExternalServiceError):
        return ChatError(503, f"Serviço indisponível — {error.service}: {error.message}")
    if isinstance(error, ChatTimeoutError):
        return ChatError(504, str(error))
    return ChatError(502, explain_error(error))


async def answer_question_async(request: ChatRequest, user: CurrentUser) -> ChatResponse:
    new_session = not request.session_id
    session_id = request.session_id or str(uuid.uuid4())
    trace.log("chat.pergunta", sessao=session_id[-8:], nova_sessao=new_session, chars=len(request.question),
              debug=request.debug)
    try:
        result = await Orchestrator(_memory_key(session_id, user)).aprocess(request.question)
    except Exception as e:
        error = _to_chat_error(e)
        trace.log("chat.ERRO", 40, status=error.status_code, erro=type(e).__name__, detalhe=trace.redact(error.message))
        raise error from e

    trace.log("chat.resposta", rota=result.route, chars=len(result.answer))
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
    trace.log("chat.sessao_encerrada", sessao=session_id[-8:], existia=existed)
    return existed
