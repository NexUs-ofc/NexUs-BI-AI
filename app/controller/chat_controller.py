"""Chat endpoints. They only receive the request, call the service and return the response."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

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
def ask(request: ChatRequest, user: User) -> ChatResponse:
    try:
        return chat_service.answer_question(request, user)
    except chat_service.LLMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.delete("/{session_id}", response_model=SessionClosedResponse)
def end_session(session_id: str, user: User) -> SessionClosedResponse:
    return SessionClosedResponse(session_id=session_id, closed=chat_service.end_session(session_id, user))
