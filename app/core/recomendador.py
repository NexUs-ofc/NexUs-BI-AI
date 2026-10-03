"""Agente Recomendador: percepções e insights. NÃO toma decisões."""
from app.core.base import criar_chain
from app.prompts.analista import SEM_DADOS
from app.prompts.recomendador import RECOMENDADOR_PROMPT
from app.schemas.agentes import RespostaEspecialista


def agente_recomendador(usuario: str, historico: list, dados: str = "") -> RespostaEspecialista:
    # `dados` virá das tools de banco quando elas forem definidas (ver core/orquestrador.py)
    contexto = dados or SEM_DADOS
    resposta = criar_chain(RECOMENDADOR_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=dados)
