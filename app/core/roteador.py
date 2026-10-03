"""Agente Roteador: decide qual especialista atende a pergunta."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import ValidationError

from app.model.llm import get_llm
from app.prompts.roteador import ROTEADOR_PROMPT
from app.schemas.agentes import DecisaoRota

prompt = ChatPromptTemplate.from_messages([
    ("system", ROTEADOR_PROMPT),
    MessagesPlaceholder("historico"),
    ("human", "{usuario}"),
])


def rotear(usuario: str, historico: list) -> DecisaoRota:
    chain = prompt | get_llm(temperature=0).with_structured_output(DecisaoRota)
    try:
        decisao = chain.invoke({"usuario": usuario, "historico": historico})
    except ValidationError:
        decisao = None
    # Erros de API (cota, chave, rede) sobem para quem chamou mostrar a mensagem real.
    if decisao is None:  # LLM respondeu fora do formato esperado
        return DecisaoRota(rota="faq", motivo="fallback: saída do roteador fora do formato")
    return decisao
