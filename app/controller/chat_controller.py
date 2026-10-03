"""Chat endpoints. They only receive the request, call the service and return the response."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.api_key import verify_api_key
from app.schemas.api import ChatRequest, ChatResponse, SessionClosedResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=ChatResponse)
def ask(request: ChatRequest) -> ChatResponse:
    try:
        return chat_service.answer_question(request)
    except chat_service.LLMError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.delete("/{session_id}", response_model=SessionClosedResponse)
def end_session(session_id: str) -> SessionClosedResponse:
    return SessionClosedResponse(session_id=session_id, closed=chat_service.end_session(session_id))
