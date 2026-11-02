"""Orchestrator: the full path of one chat message, in plain Python.

    input guardrail (rules, no LLM) --blocked--> answer with the reason
          |
    assistant (1 agent: Gemini + FAQ/report tools) <---------------+
          |                                                        | a number of the answer is not in
    number check (code, no LLM) -----------------------------------+ the data and retries are left
          |
    finish: output guardrail + session memory

Gemini calls per question: 1 without tools (greeting, BI concept), usually 2 with one tool (call the tool,
then answer). The old graph used router + specialist + LLM judge: 4 to 12 sequential calls.

Every stage is logged with its time (observability/trace.py) and timed for the admin panel
(state["timings"], saved in metrics_bi by observability/metrics.py).
"""
import asyncio
import threading
import time

from langchain_core.callbacks import get_usage_metadata_callback
from langsmith import traceable

from app.config import CHAT_TIMEOUT_S, MAX_JUDGE_RETRIES
from app.core.assistant import assistant_agent
from app.core.memory import get_session_history
from app.core.prompts.orchestrator import REJECTED_ANSWER, REVISION
from app.guardrails.guardrails import input_guardrail, output_guardrail
from app.observability import trace
from app.observability.metrics import ToolMetricsCallback, new_trace_id, record_question
from app.schemas.agents import Result
from app.tools.judge_tools import format_numbers, missing_numbers


class ChatTimeoutError(Exception):
    """The whole message took longer than CHAT_TIMEOUT_S."""


def _timed(state: dict, node: str, started: float) -> None:
    """Time of a stage for the admin panel (same node names as before: the panel groups them by stage)."""
    state["timings"].append({"node": node, "ms": (time.perf_counter() - started) * 1000})


class Orchestrator:
    def __init__(self, session_id: str):
        self.session_id = session_id

    @traceable(name="orchestrator")
    def process(self, message: str) -> Result:
        started = time.perf_counter()
        trace_id = new_trace_id()
        tools = ToolMetricsCallback(trace_id)  # records every tool call of this question
        state: dict = {"steps": [], "timings": [], "attempts": 0}
        error: Exception | None = None
        # get_usage_metadata_callback adds up the tokens of every Gemini call made inside the block
        with get_usage_metadata_callback() as usage:
            try:
                self._run(message, state, tools)
            except Exception as e:
                error = e
                raise
            finally:
                _record_in_background(trace_id, dict(state), started, dict(usage.usage_metadata),
                                      list(tools.tool_calls), error)
        return Result(answer=state["answer"], route=state["route"], steps=state["steps"])

    def _run(self, message: str, state: dict, tools: ToolMetricsCallback) -> None:
        with trace.step("memoria.leitura", sessao=self.session_id[-8:]) as info:
            history = get_session_history(self.session_id).messages
            info["mensagens"] = len(history)

        t0 = time.perf_counter()
        with trace.step("guardrail.entrada", chars=len(message)) as info:
            guard = input_guardrail(message)
            info["permitido"] = guard.allowed
        _timed(state, "input_guardrail", t0)
        if not guard.allowed:
            state.update(route="blocked", answer=guard.reason, approved=False)
            state["steps"].append(f"guardrail de entrada: BLOQUEADO ({guard.reason})")
            return
        question = guard.text
        masked = " (dados pessoais mascarados)" if question != message.strip() else ""
        state["steps"].append(f"guardrail de entrada: ok{masked}")

        current_input, answer, approved = question, "", False
        while True:
            state["attempts"] += 1
            t0 = time.perf_counter()
            with trace.step("agente", tentativa=state["attempts"], historico=len(history)) as info:
                output = assistant_agent(current_input, history, config={"callbacks": [tools]})
                info.update(rota=output.route, tools=",".join(c.split("(", 1)[0] for c in output.tool_calls) or None,
                            chars_contexto=len(output.context), chars_resposta=len(output.answer))
            _timed(state, "specialist", t0)
            answer, state["route"] = output.answer, output.route
            if output.tool_calls:
                state["steps"].append(f"tools: {', '.join(output.tool_calls)}")

            t0 = time.perf_counter()
            with trace.step("conferencia.numeros") as info:
                missing = missing_numbers(answer, output.context) if output.context else []
                info["fora_dos_dados"] = format_numbers(missing) or None
            _timed(state, "judge", t0)
            approved = not missing
            state["steps"].append(
                "conferência de números: ok" if approved
                else f"conferência de números: fora dos dados -> {format_numbers(missing)}"
            )
            if approved or state["attempts"] > MAX_JUDGE_RETRIES:
                break
            current_input = REVISION.format(question=question, numbers=format_numbers(missing), previous_answer=answer)

        t0 = time.perf_counter()
        final = answer if approved else REJECTED_ANSWER
        with trace.step("guardrail.saida") as info:
            guard = output_guardrail(final)
            info["permitido"] = guard.allowed
        state["steps"].append("guardrail de saída: ok" if guard.allowed else f"guardrail de saída: BLOQUEADO ({guard.reason})")
        with trace.step("memoria.gravacao", sessao=self.session_id[-8:]) as info:
            session = get_session_history(self.session_id)
            session.add_user_message(question)
            session.add_ai_message(guard.text)
            info["mensagens"] = len(session.messages)
        _timed(state, "finish", t0)
        state.update(answer=guard.text, approved=approved, output_blocked=not guard.allowed)

    async def aprocess(self, message: str) -> Result:
        """Runs process() in a worker thread (the event loop stays free for other requests)."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(self.process, message), timeout=CHAT_TIMEOUT_S)
        except TimeoutError as e:
            trace.log("chat.TIMEOUT", 40, limite_s=CHAT_TIMEOUT_S,
                      nota="a thread em andamento termina sozinha; a resposta dela é descartada")
            raise ChatTimeoutError(
                f"O assistente excedeu o tempo limite de {CHAT_TIMEOUT_S:.0f}s. Tente novamente em instantes."
            ) from e


def _record_in_background(*args) -> None:
    """The metric is written to MongoDB after the answer, so the user never waits for it."""
    trace_context = trace.current()

    def run() -> None:
        trace.attach(trace_context)
        with trace.step("metricas.gravacao"):  # off the critical path: not added to the request's mongodb_ms
            record_question(*args)

    threading.Thread(target=run, name="metrics-writer", daemon=True).start()
