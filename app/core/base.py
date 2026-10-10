"""Shared base for the specialist agents: system prompt + history + question."""
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.model.llm import get_llm

MAX_TOOL_ROUNDS = 4  # how many times the agent may call tools before it must answer


def _build_prompt(system_prompt: str) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),        # system prompt
        MessagesPlaceholder("history"),   # session memory
        ("human", "{question}"),          # user question
    ])


def build_chain(system_prompt: str, temperature: float | None = None):
    return _build_prompt(system_prompt) | get_llm(temperature) | StrOutputParser()


def _text(message: AIMessage) -> str:
    """Gemini may return the content as a list of parts; keep only the text."""
    if isinstance(message.content, str):
        return message.content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in message.content)


def run_with_tools(
    system_prompt: str, question: str, history: list, tools: list[BaseTool], **variables
) -> tuple[str, list[str], list[str]]:
    """Run the agent letting the LLM call the tools it needs.

    Returns (final answer, tool log, tool calls). The tool log is what the tools returned (judge context).
    """
    messages = _build_prompt(system_prompt).format_messages(question=question, history=history, **variables)
    llm_with_tools = get_llm().bind_tools(tools)
    tools_by_name = {t.name: t for t in tools}
    tool_log: list[str] = []
    tool_calls: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        reply = llm_with_tools.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            return _text(reply), tool_log, tool_calls
        for call in reply.tool_calls:
            tool = tools_by_name.get(call["name"])
            output = tool.invoke(call["args"]) if tool else f"Tool desconhecida: {call['name']}"
            tool_calls.append(f"{call['name']}({call['args']})")
            tool_log.append(f"{call['name']}({call['args']}) -> {output}")
            messages.append(ToolMessage(content=str(output), tool_call_id=call["id"]))

    # Tool budget exhausted: ask for a final answer without tools
    return _text(get_llm().invoke(messages)), tool_log, tool_calls
