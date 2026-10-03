"""Agente Analista descritivo: verifica insights da base de dados."""
from app.core.base import criar_chain
from app.schemas.agentes import RespostaEspecialista
from app.tools.dados_tool import resumo_base

SYSTEM_PROMPT = """Você é o ANALISTA DESCRITIVO de BI da NexUs.
Responda à pergunta usando APENAS o resumo da base abaixo (os números já foram calculados em código).
Regras:
- Não invente números; se a informação não estiver no resumo, diga que a base não permite responder.
- Seja descritivo: o que aconteceu, onde, quanto. Não recomende ações (isso é papel do Recomendador).
- Cite os números usados.

=== RESUMO DA BASE ===
{contexto}
=== FIM ==="""


def agente_analista(usuario: str, historico: list) -> RespostaEspecialista:
    contexto = resumo_base()
    resposta = criar_chain(SYSTEM_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=contexto)
