"""Agente Juiz (LLM-as-a-judge): avalia se a resposta é fiel ao contexto e respeita o papel do agente."""
from langchain_core.prompts import ChatPromptTemplate

from app.model.llm import get_llm
from app.prompts.juiz import JUIZ_ENTRADA, JUIZ_PROMPT
from app.schemas.agentes import Veredito

prompt = ChatPromptTemplate.from_messages([
    ("system", JUIZ_PROMPT),
    ("human", JUIZ_ENTRADA),
])


def julgar(pergunta: str, resposta: str, contexto: str, agente: str) -> Veredito:
    chain = prompt | get_llm(temperature=0).with_structured_output(Veredito)
    try:
        veredito = chain.invoke({"pergunta": pergunta, "resposta": resposta, "contexto": contexto or "(vazio)", "agente": agente})
    except Exception as e:  # noqa: BLE001 - não trava o fluxo se o juiz falhar
        return Veredito(aprovado=True, nota=-1, motivo=f"juiz indisponível: {e}")
    return veredito or Veredito(aprovado=True, nota=-1, motivo="juiz respondeu fora do formato")
