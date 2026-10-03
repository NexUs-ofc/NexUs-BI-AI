"""Service de chat: a ponte entre o controller (HTTP) e o Orquestrador (agentes)."""
import uuid

from app.core.memory import limpar_sessao, store
from app.core.orquestrador import Orquestrador
from app.model.llm import explicar_erro
from app.schemas.api import ChatRequest, ChatResponse


class ErroLLM(Exception):
    """Falha ao falar com o modelo (cota, chave, indisponibilidade...)."""


def responder(requisicao: ChatRequest) -> ChatResponse:
    session_id = requisicao.session_id or str(uuid.uuid4())
    try:
        resultado = Orquestrador(session_id).processar(requisicao.pergunta)
    except Exception as e:  # noqa: BLE001
        raise ErroLLM(explicar_erro(e)) from e

    return ChatResponse(
        session_id=session_id,
        resposta=resultado.resposta,
        rota=resultado.rota,
        passos=resultado.passos if requisicao.debug else None,
    )


def encerrar_sessao(session_id: str) -> bool:
    """Apaga a memória da sessão. Devolve False se ela não existia."""
    existia = session_id in store
    limpar_sessao(session_id)
    return existia
