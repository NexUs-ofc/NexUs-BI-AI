"""Agente Recomendador: percepções e insights. NÃO toma decisões."""
from app.core.base import criar_chain
from app.schemas.agentes import RespostaEspecialista
from app.tools.dados_tool import resumo_base

AVISO = (
    "⚠️ Estas são percepções e insights gerados a partir dos dados. "
    "Não são decisões: a decisão final é sempre da equipe responsável."
)

SYSTEM_PROMPT = """Você é o RECOMENDADOR de BI da NexUs.
Seu papel é apontar PERCEPÇÕES e INSIGHTS a partir do resumo da base abaixo.
Regras:
- Você NÃO toma decisões e NÃO dá ordens. Use linguagem como "os dados sugerem", "pode valer avaliar", "um ponto de atenção é".
- Toda sugestão deve citar o dado que a sustenta.
- Não invente números fora do resumo.
- Termine listando 2 a 3 perguntas que a equipe poderia investigar.

=== RESUMO DA BASE ===
{contexto}
=== FIM ==="""


def agente_recomendador(usuario: str, historico: list) -> RespostaEspecialista:
    contexto = resumo_base()
    resposta = criar_chain(SYSTEM_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=contexto)
