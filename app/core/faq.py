"""Agente de FAQ: responde dúvidas gerais com base no FAQ indexado no Qdrant."""
from app.config import FAQ_LIMITE
from app.core.base import criar_chain
from app.prompts.faq import FAQ_PROMPT, SEM_FAQ
from app.repository.faq_repository import buscar_faq
from app.schemas.agentes import RespostaEspecialista


def _formatar(itens: list[dict]) -> str:
    return "\n\n".join(f"P: {i.get('pergunta', '')}\nR: {i.get('resposta', '')}" for i in itens)


def agente_faq(usuario: str, historico: list) -> RespostaEspecialista:
    contexto = _formatar(buscar_faq(usuario, FAQ_LIMITE)) or SEM_FAQ
    resposta = criar_chain(FAQ_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=contexto)
