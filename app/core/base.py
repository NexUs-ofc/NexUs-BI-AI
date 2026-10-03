"""Base comum dos agentes especialistas: system prompt + histórico + pergunta."""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.model.llm import get_llm


def criar_chain(system_prompt: str, temperature: float | None = None):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),          # system prompt
        MessagesPlaceholder("historico"),   # memória da sessão
        ("human", "{usuario}"),             # pergunta do usuário
    ])
    return prompt | get_llm(temperature) | StrOutputParser()
