"""Orchestrator: coordinates the full flow of one message as a LangGraph graph (StateGraph).

    START -> input_guardrail --(blocked)--> END
                    | ok
                  router --(out_of_scope)--> finish
                    |
                specialist <-----------------+
                    |                        | rejected and retries left
                  judge ---------------------+
                    | approved / no retries left
                  finish (output guardrail + session memory) -> END

Each node receives the state, does one job and returns only the fields it changed.
The decisions (blocked? out of scope? retry?) are conditional edges.
@traceable sends each node to LangSmith when LANGSMITH_TRACING=true (see config.py).
@timed measures each node, and process() saves one metric document per question (observability/metrics.py).

Print the graph as a Mermaid diagram (from the project root):
    python -m app.core.orchestrator
"""
import asyncio
import datetime
import operator
import re
import time
from typing import Annotated, TypedDict

from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from app.config import MAX_JUDGE_RETRIES
from app.core.analyst import analyst_agent
from app.core.faq import faq_agent
from app.core.judge import judge
from app.core.memory import get_session_history
from app.core.prompts.orchestrator import (
    JUDGE_REVISION,
    OUT_OF_SCOPE_ANSWER,
    REJECTED_ANSWER,
)
from app.core.prompts.recommender import RECOMMENDER_DISCLAIMER
from app.core.recommender import recommender_agent
from app.core.router import route
from app.guardrails.guardrails import input_guardrail, output_guardrail
from app.observability.metrics import (
    ToolMetricsCallback,
    new_trace_id,
    record_question,
    timed,
)
from app.schemas.agents import Result

SPECIALISTS = {
    "faq": faq_agent,
    "analyst": analyst_agent,
    "recommender": recommender_agent,
}


class ChatState(TypedDict, total=False):
    """Everything the nodes share while one message goes through the graph."""

    session_id: str
    message: str        # text sent by the user
    question: str       # text after the input guardrail (personal data masked)
    history: list       # previous messages of the session
    route: str          # faq | analyst | recommender | out_of_scope | blocked
    current_input: str  # what the specialist receives (question, or question + judge feedback)
    answer: str
    context: str        # source of truth used by the specialist (sent to the judge)
    attempts: int       # how many times the specialist ran
    approved: bool
    output_blocked: bool  # the output guardrail replaced the answer
    steps: Annotated[list[str], operator.add]  # debug trace; each node appends to it
    timings: Annotated[list[dict], operator.add]  # how long each node took (filled by @timed)
    is_greeting: bool     # set by input_guardrail; skips router + judge when True



def _log(node: str, msg: str = "") -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [{node}] {msg}", flush=True)

# ---------------------------------------------------------------- greeting detection

_GREETING_RE = re.compile(
    r"^(oi|ol[aá]|ei|hey|hi+|hello|bom\s?dia|boa\s?tarde|boa\s?noite"
    r"|tudo\s?bem|tudo\s?bom|como\s?vai|como\s?est[aá]|e\s?a[ií]|eae|opa"
    r"|good\s?morning|good\s?afternoon|good\s?evening|howdy|what'?s\s?up|sup"
    r"|oi,?\s?tudo|ol[aá],?\s?tudo|oi\s+assistente|ol[aá]\s+assistente)"
    r"[\s!?.]*$",
    re.IGNORECASE,
)

def _is_greeting(text: str) -> bool:
    """True for short conversational openers that need no data lookup or judge review."""
    return bool(_GREETING_RE.match(text.strip())) and len(text.split()) <= 10


# ---------------------------------------------------------------- nodes

@traceable(name="input_guardrail")
@timed("input_guardrail")
def input_guardrail_node(state: ChatState) -> dict:
    _log("input_guardrail", f"mensagem={state['message']!r:.60}")
    guard = input_guardrail(state["message"])
    if not guard.allowed:
        return {"route": "blocked", "answer": guard.reason, "steps": [f"guardrail de entrada: BLOQUEADO ({guard.reason})"]}
    masked = " (dados pessoais mascarados)" if guard.text != state["message"].strip() else ""
    greeting = _is_greeting(guard.text)
    return {
        "question": guard.text,
        "current_input": guard.text,
        "attempts": 0,
        "is_greeting": greeting,
        "steps": [f"guardrail de entrada: ok{masked}"],
    }


@traceable(name="router")
@timed("router")
def router_node(state: ChatState) -> dict:
    _log("router", f"question={state['question']!r:.60}")
    decision = route(state["question"], state["history"])
    _log("router", f"decisão={decision.route}")
    update = {"route": decision.route, "steps": [f"roteador: {decision.route} ({decision.reason})"]}
    if decision.route == "out_of_scope":
        update.update(answer=OUT_OF_SCOPE_ANSWER, approved=True)
    return update


@traceable(name="specialist")
@timed("specialist")
def specialist_node(state: ChatState) -> dict:
    _log("specialist", f"route={state['route']}")
    output = SPECIALISTS[state["route"]](state["current_input"], state["history"])
    _log("specialist", "resposta recebida")
    steps = [f"tools: {', '.join(output.tool_calls)}"] if output.tool_calls else []
    return {"answer": output.answer, "context": output.context, "attempts": state["attempts"] + 1, "steps": steps}


@traceable(name="greeting")
@timed("specialist")
def greeting_node(state: ChatState) -> dict:
    _log("greeting", "chamando LLM...")
    """Fast path for conversational openers: skip router and judge.
    Uses faq_agent directly (no router LLM call) and auto-approves (no judge LLM call).
    Saves ~2 Interactions API round-trips (~80s) per greeting.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.model.llm import get_llm
    llm = get_llm()
    greeting_system = (
        "Você é o assistente do NexUs BI, sistema de Business Intelligence. "
        "O usuário está cumprimentando. Responda de forma cordial e breve "
        "e informe o que você pode ajudar (dúvidas sobre BI, relatórios, dados da empresa). "
        "Não use markdown."
    )
    response = llm.invoke([SystemMessage(content=greeting_system), HumanMessage(content=state["question"])])
    _log("greeting", "LLM respondeu")
    return {
        "route": "faq",
        "answer": response.content,
        "context": "",
        "attempts": 1,
        "approved": True,
        "steps": ["roteador: faq (cumprimento — rota rápida)", "juiz: pulado (cumprimento)"],
    }


@traceable(name="judge")
@timed("judge")
def judge_node(state: ChatState) -> dict:
    _log("judge", f"tentativa={state['attempts']}")
    verdict = judge(state["question"], state["answer"], state["context"], state["route"], state["history"])
    steps = [f"validação de números: {verdict.number_check}"]
    if verdict.tool_calls:
        steps.append(f"tools do juiz: {', '.join(verdict.tool_calls)}")
    steps.append(
        f"juiz (tentativa {state['attempts']}): {'aprovado' if verdict.approved else 'reprovado'} "
        f"nota={verdict.score} - {verdict.reason}"
    )
    update = {"approved": verdict.approved, "steps": steps}
    if not verdict.approved:  # feedback for the next attempt
        update["current_input"] = JUDGE_REVISION.format(
            question=state["question"], previous_answer=state["answer"], reason=verdict.reason
        )
    return update


@traceable(name="finish")
@timed("finish")
def finish_node(state: ChatState) -> dict:
    _log("finish")
    answer = state["answer"] if state["approved"] else REJECTED_ANSWER
    if state["route"] == "recommender" and state["approved"]:
        answer = f"{answer}\n\n{RECOMMENDER_DISCLAIMER}"
    guard = output_guardrail(answer)
    answer = guard.text
    step = "guardrail de saída: ok" if guard.allowed else f"guardrail de saída: BLOQUEADO ({guard.reason})"

    # Session memory: sanitized question + final answer
    history = get_session_history(state["session_id"])
    history.add_user_message(state["question"])
    history.add_ai_message(answer)
    return {"answer": answer, "output_blocked": not guard.allowed, "steps": [step]}


# ---------------------------------------------------------------- conditional edges

def after_input_guardrail(state: ChatState) -> str:
    if state.get("route") == "blocked":
        return END
    if state.get("is_greeting"):
        return "greeting"  # skip router + judge
    return "router"


def after_router(state: ChatState) -> str:
    return "finish" if state["route"] == "out_of_scope" else "specialist"


def after_judge(state: ChatState) -> str:
    if state["approved"] or state["attempts"] > MAX_JUDGE_RETRIES:
        return "finish"
    return "specialist"  # rejected: try again with the judge feedback


# ---------------------------------------------------------------- graph

def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("input_guardrail", input_guardrail_node)
    graph.add_node("router", router_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("specialist", specialist_node)
    graph.add_node("judge", judge_node)
    graph.add_node("finish", finish_node)

    graph.add_edge(START, "input_guardrail")
    graph.add_conditional_edges("input_guardrail", after_input_guardrail, ["router", "greeting", END])
    graph.add_conditional_edges("router", after_router, ["specialist", "finish"])
    graph.add_edge("greeting", "finish")  # greeting is always approved, goes straight to finish
    graph.add_edge("specialist", "judge")
    graph.add_conditional_edges("judge", after_judge, ["specialist", "finish"])
    graph.add_edge("finish", END)
    return graph.compile()


GRAPH = build_graph()


class Orchestrator:
    def __init__(self, session_id: str):
        self.session_id = session_id

    @traceable(name="orchestrator")
    def process(self, message: str) -> Result:
        started, state, error = time.perf_counter(), None, None
        trace_id = new_trace_id()
        tools = ToolMetricsCallback(trace_id)  # records every tool call of this question
        # get_usage_metadata_callback adds up the tokens of every Gemini call made inside the block
        with get_usage_metadata_callback() as usage:
            try:
                state = GRAPH.invoke(
                    {
                        "session_id": self.session_id,
                        "message": message,
                        "history": get_session_history(self.session_id).messages,
                        "steps": [],
                        "timings": [],
                    },
                    config={"callbacks": [tools]},
                )
            except Exception as e:
                error = e
                raise
            finally:
                record_question(trace_id, state, started, usage.usage_metadata, tools.tool_calls, error)
        return Result(answer=state["answer"], route=state["route"], steps=state["steps"])

    # Timeout global para evitar que o grafo fique preso indefinidamente
    # (ex: modelo travado, API sem resposta, quota silenciosa).
    _GRAPH_TIMEOUT_S: int = 85

    async def aprocess(self, message: str) -> Result:
        """Async version: uses ainvoke so multiple sessions run concurrently."""
        started, state, error = time.perf_counter(), None, None
        _log("aprocess", f"mensagem={message!r:.60}")
        trace_id = new_trace_id()
        tools = ToolMetricsCallback(trace_id)
        with get_usage_metadata_callback() as usage:
            try:
                state = await asyncio.wait_for(
                    GRAPH.ainvoke(
                        {
                            "session_id": self.session_id,
                            "message": message,
                            "history": get_session_history(self.session_id).messages,
                            "steps": [],
                            "timings": [],
                        },
                        config={"callbacks": [tools]},
                    ),
                    timeout=self._GRAPH_TIMEOUT_S,
                )
            except asyncio.TimeoutError as e:
                error = e
                raise RuntimeError(
                    f"O assistente excedeu o tempo limite de {self._GRAPH_TIMEOUT_S}s. "
                    "Tente novamente em instantes."
                ) from e
            except Exception as e:
                error = e
                raise
            finally:
                record_question(trace_id, state, started, usage.usage_metadata, tools.tool_calls, error)
        return Result(answer=state["answer"], route=state["route"], steps=state["steps"])


if __name__ == "__main__":
    print(GRAPH.get_graph().draw_mermaid())
