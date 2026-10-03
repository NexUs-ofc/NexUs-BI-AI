"""Agente Juiz (LLM-as-a-judge): avalia se a resposta é fiel ao contexto e respeita o papel do agente."""
from langchain_core.prompts import ChatPromptTemplate

from app.model.llm import get_llm
from app.schemas.agentes import Veredito

SYSTEM_PROMPT = """Você é o JUIZ de qualidade de um assistente de BI.
Avalie a RESPOSTA para a PERGUNTA, considerando o CONTEXTO (fonte da verdade) e o AGENTE que respondeu.

Reprove se:
- Houver números ou fatos que não estão no contexto (alucinação).
- O agente "recomendador" apresentar algo como decisão/ordem em vez de percepção/insight.
- O agente "analista" fizer recomendações em vez de descrever os dados.
- A resposta não responder à pergunta ou contiver dados pessoais (CPF, e-mail, telefone).

Se o contexto estiver vazio (ex.: saudação), avalie apenas educação e coerência."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "AGENTE: {agente}\n\nPERGUNTA: {pergunta}\n\nCONTEXTO:\n{contexto}\n\nRESPOSTA:\n{resposta}"),
])


def julgar(pergunta: str, resposta: str, contexto: str, agente: str) -> Veredito:
    chain = prompt | get_llm(temperature=0).with_structured_output(Veredito)
    try:
        return chain.invoke({"pergunta": pergunta, "resposta": resposta, "contexto": contexto or "(vazio)", "agente": agente})
    except Exception as e:  # noqa: BLE001 - não trava o fluxo se o juiz falhar
        return Veredito(aprovado=True, nota=-1, motivo=f"juiz indisponível: {e}")
