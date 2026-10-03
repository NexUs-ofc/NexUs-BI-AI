"""Agente de FAQ: perguntas estáticas gerais."""
from app.core.base import criar_chain
from app.schemas.agentes import RespostaEspecialista
from app.tools.faq_tool import faq_como_texto

SYSTEM_PROMPT = """Você é o agente de FAQ da NexUs.
Responda SOMENTE com base nas perguntas frequentes abaixo. Se a resposta não estiver nelas,
diga que não encontrou essa informação no FAQ e sugira reformular ou perguntar sobre os dados.
Para saudações simples, cumprimente e explique que pode responder dúvidas gerais, analisar os dados e dar recomendações.

=== FAQ ===
{contexto}
=== FIM FAQ ==="""

SEM_FAQ = "(FAQ ainda não cadastrado.)"


def agente_faq(usuario: str, historico: list) -> RespostaEspecialista:
    contexto = faq_como_texto() or SEM_FAQ
    resposta = criar_chain(SYSTEM_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=contexto)
