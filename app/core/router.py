"""Router agent: decides which specialist handles the question."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import ValidationError

from app.model.llm import get_llm
from app.prompts.router import ROUTER_PROMPT
from app.schemas.agents import RouteDecision

prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTER_PROMPT),
    MessagesPlaceholder("history"),
    ("human", "{question}"),
])


def route(question: str, history: list) -> RouteDecision:
    chain = prompt | get_llm(temperature=0).with_structured_output(RouteDecision)
    try:
        decision = chain.invoke({"question": question, "history": history})
    except ValidationError:
        decision = None
    # API errors (quota, key, network) bubble up so the caller can show the real message.
    if decision is None:  # the LLM answered outside the expected format
        return RouteDecision(route="faq", reason="fallback: saída do roteador fora do formato")
    return decision
