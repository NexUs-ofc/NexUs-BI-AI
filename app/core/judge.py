"""Judge agent (LLM-as-a-judge): checks that the answer is faithful to the context and respects the agent's role."""
from langchain_core.prompts import ChatPromptTemplate

from app.model.llm import get_llm
from app.prompts.judge import JUDGE_INPUT, JUDGE_PROMPT
from app.schemas.agents import Verdict

prompt = ChatPromptTemplate.from_messages([
    ("system", JUDGE_PROMPT),
    ("human", JUDGE_INPUT),
])


def judge(question: str, answer: str, context: str, agent: str) -> Verdict:
    chain = prompt | get_llm(temperature=0).with_structured_output(Verdict)
    try:
        verdict = chain.invoke({"question": question, "answer": answer, "context": context or "(vazio)", "agent": agent})
    except Exception as e:  # noqa: BLE001 - never block the flow if the judge fails
        return Verdict(approved=True, score=-1, reason=f"juiz indisponível: {e}")
    return verdict or Verdict(approved=True, score=-1, reason="juiz respondeu fora do formato")
