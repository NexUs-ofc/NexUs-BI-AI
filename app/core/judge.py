"""Judge agent (LLM-as-a-judge): checks that the answer is faithful to the context and respects the agent's role.

Built with create_agent: structured output (Verdict) + validation (tools/judge_tools.py). The number check
always runs in code and goes in the judge input; search_context is a tool the judge may call.
"""
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.base import build_agent, run_agent, structured_output, tool_trace
from app.core.prompts.judge import EMPTY_CONTEXT, JUDGE_INPUT, JUDGE_PROMPT, NO_HISTORY
from app.schemas.agents import JudgeResult, Verdict
from app.tools.judge_tools import build_judge_tools, check_numbers

HISTORY_MESSAGES = 6  # only the last messages help the judge understand follow-up questions
MIN_SCORE = 7  # an answer is approved only with approved=True AND score >= MIN_SCORE


def _format_history(history: list[BaseMessage]) -> str:
    lines = [
        f"{'Usuário' if isinstance(m, HumanMessage) else 'Assistente'}: {m.content}"
        for m in history[-HISTORY_MESSAGES:]
    ]
    return "\n".join(lines) or NO_HISTORY


def judge(
    question: str, answer: str, context: str, agent: str, history: list[BaseMessage] | None = None
) -> JudgeResult:
    number_check = check_numbers(answer, context)
    judge_input = JUDGE_INPUT.format(
        number_check=number_check,
        agent=agent,
        history=_format_history(history or []),
        question=question,
        context=context or EMPTY_CONTEXT,
        answer=answer,
    )
    tools = build_judge_tools(context)
    try:
        state = run_agent(build_agent(JUDGE_PROMPT, tools, response_format=Verdict, temperature=0), judge_input)
    except Exception as e:  # noqa: BLE001 - never block the flow if the judge fails
        return JudgeResult(approved=True, score=-1, reason=f"juiz indisponível: {e}", number_check=number_check)

    verdict: Verdict | None = structured_output(state)
    if verdict is None:
        return JudgeResult(approved=True, score=-1, reason="juiz respondeu fora do formato", number_check=number_check)
    calls, _ = tool_trace(state, tools)
    return JudgeResult(
        approved=verdict.approved and verdict.score >= MIN_SCORE,
        score=verdict.score,
        reason=verdict.reason,
        tool_calls=calls,
        number_check=number_check,
    )
