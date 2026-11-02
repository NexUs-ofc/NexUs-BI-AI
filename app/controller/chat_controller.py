"""Chat endpoints. They only receive the request, call the service and return the response."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.schemas.api import (
    ChatRequest,
    ChatResponse,
    CurrentUser,
    SessionClosedResponse,
)
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

User = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("", response_model=ChatResponse)
async def ask(request: ChatRequest, user: User) -> ChatResponse:
    """The message runs in a worker thread: the event loop keeps serving other requests."""
    try:
        return await chat_service.answer_question_async(request, user)
    except chat_service.ChatError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.delete("/{session_id}", response_model=SessionClosedResponse)
def end_session(session_id: str, user: User) -> SessionClosedResponse:
    return SessionClosedResponse(session_id=session_id, closed=chat_service.end_session(session_id, user))
