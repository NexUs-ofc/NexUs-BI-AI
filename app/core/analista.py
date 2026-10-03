"""Agente Analista descritivo: descreve o que os dados da empresa mostram."""
from app.core.base import criar_chain
from app.prompts.analista import ANALISTA_PROMPT, SEM_DADOS
from app.schemas.agentes import RespostaEspecialista


def agente_analista(usuario: str, historico: list, dados: str = "") -> RespostaEspecialista:
    # `dados` virá das tools de banco quando elas forem definidas (ver core/orquestrador.py)
    contexto = dados or SEM_DADOS
    resposta = criar_chain(ANALISTA_PROMPT).invoke({"usuario": usuario, "historico": historico, "contexto": contexto})
    return RespostaEspecialista(resposta=resposta, contexto=dados)
