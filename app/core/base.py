"""Shared base for the specialist agents: system prompt + history + question."""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.model.llm import get_llm


def build_chain(system_prompt: str, temperature: float | None = None):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),        # system prompt
        MessagesPlaceholder("history"),   # session memory
        ("human", "{question}"),          # user question
    ])
    return prompt | get_llm(temperature) | StrOutputParser()
