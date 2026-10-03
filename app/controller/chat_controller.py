"""Endpoints de chat. Só recebe o pedido, chama o service e devolve a resposta."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.api_key import verificar_api_key
from app.schemas.api import ChatRequest, ChatResponse, SessaoEncerradaResponse
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(verificar_api_key)])


@router.post("", response_model=ChatResponse)
def perguntar(requisicao: ChatRequest) -> ChatResponse:
    try:
        return chat_service.responder(requisicao)
    except chat_service.ErroLLM as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.delete("/{session_id}", response_model=SessaoEncerradaResponse)
def encerrar(session_id: str) -> SessaoEncerradaResponse:
    return SessaoEncerradaResponse(session_id=session_id, encerrada=chat_service.encerrar_sessao(session_id))
