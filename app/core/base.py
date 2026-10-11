"""Shared base for every agent, built with LangChain's create_agent.

create_agent (LangChain 1.x) builds the ReAct loop for us: the LLM decides whether to call a tool,
the tool runs, its result goes back to the LLM, and so on until a final answer.

- build_agent: creates the agent (system prompt + tools + optional structured output).
- run_agent: sends the session history + the question and returns the final state.
- final_text / structured_output / tool_trace: read what we need from that state.
"""
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.model.llm import get_llm
from app.prompts.orchestrator import LIMIT_REACHED_ANSWER

MAX_TOOL_CALLS = 4  # tool calls allowed per question; after that the agent must answer with what it has
MAX_MODEL_CALLS = 8  # LLM calls allowed per question; protects against loops (and API cost)


def build_agent(system_prompt: str, tools: list[BaseTool] | None = None, response_format=None, temperature=None):
    """Create an agent.

    response_format: a pydantic class when the answer must follow a schema (router and judge).
    ToolStrategy delivers the schema as a tool, which works together with the agent's other tools on Gemini.
    """
    return create_agent(
        model=get_llm(temperature),
        tools=tools or [],
        system_prompt=system_prompt,
        response_format=ToolStrategy(response_format) if response_format else None,
        middleware=[
            ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS, exit_behavior="continue"),
        ],
    )


def run_agent(agent, question: str, history: list | None = None) -> dict:
    """Run the agent with the session history (short-term memory) followed by the new question."""
    return agent.invoke({"messages": [*(history or []), HumanMessage(content=question)]})


def _text(message: AIMessage) -> str:
    """Gemini may return the content as a list of parts; keep only the text."""
    if isinstance(message.content, str):
        return message.content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in message.content)


def final_text(state: dict) -> str:
    """Text of the agent's last message.

    When MAX_MODEL_CALLS is reached, ModelCallLimitMiddleware ends the run with an English message
    ("Model call limits exceeded..."); the user gets a Portuguese one instead.
    """
    text = _text(state["messages"][-1])
    return LIMIT_REACHED_ANSWER if text.startswith("Model call limits exceeded") else text


def structured_output(state: dict):
    """Object of the response_format class, or None if the LLM did not follow the schema."""
    return state.get("structured_response")


def tool_trace(state: dict, tools: list[BaseTool]) -> tuple[list[str], list[str]]:
    """Return (tool calls, tool log) of the given tools. The log has what each tool returned and becomes
    the judge context. Other calls (like the structured output of ToolStrategy) are ignored."""
    names = {t.name for t in tools}
    calls: dict[str, str] = {}
    log: list[str] = []
    for message in state["messages"]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["name"] in names:
                    calls[call["id"]] = f"{call['name']}({call['args']})"
        elif isinstance(message, ToolMessage) and message.tool_call_id in calls:
            log.append(f"{calls[message.tool_call_id]} -> {message.content}")
    return list(calls.values()), log
