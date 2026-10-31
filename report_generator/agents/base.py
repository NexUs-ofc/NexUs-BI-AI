"""Base comum dos agentes do gerador (mesmo padrão de app/core/base.py, sem depender do chatbot).

- get_llm: Gemini.
- build_agent: create_agent do LangChain 1.x com limites de chamadas (protege contra loop e custo).
- arun_agent / final_text / structured_output / tool_outputs: executam (assíncrono) e leem o resultado.
"""
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage, ToolMessage

from report_generator.config import GOOGLE_API_KEY, LLM_MODEL, LLM_TEMPERATURE

MAX_TOOL_CALLS = 12
MAX_MODEL_CALLS = 16

COMMON_RULES = """Regras gerais (valem sempre):
- Escreva em português do Brasil, em tom profissional e direto, para gestores de empresas.
- Todo número que você escrever precisa ter vindo de uma tool. Nunca calcule de cabeça: use as tools de
  cálculo. Nunca invente, estime ou arredonde de forma diferente da tool.
- Variação de taxa é em pontos percentuais (p.p.), não em %. Ex.: de 15,0% para 12,5% = queda de 2,5 p.p.
- Os dados são agregados de households (famílias). Nunca cite household, pessoa ou endereço individual.
- UF com suprimido=true não tem números por privacidade: diga "dados insuficientes", nunca estime.
- Use vírgula como separador decimal (12,5%)."""


def get_llm(temperature: float | None = None):
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY não definida. Preencha o .env ou rode com --sem-ia.")
    return ChatGoogleGenerativeAI(model=LLM_MODEL, google_api_key=GOOGLE_API_KEY, max_retries=2, timeout=120,
                                  temperature=LLM_TEMPERATURE if temperature is None else temperature)


def build_agent(system_prompt: str, tools=None, response_format=None, model=None):
    """`model` permite injetar outro chat model (ex.: um modelo falso nos testes)."""
    return create_agent(
        model=model or get_llm(),
        tools=tools or [],
        system_prompt=f"{system_prompt}\n\n{COMMON_RULES}",
        response_format=ToolStrategy(response_format) if response_format else None,
        middleware=[
            ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS, exit_behavior="continue"),
        ],
    )


async def arun_agent(agent, message: str) -> dict:
    return await agent.ainvoke({"messages": [HumanMessage(content=message)]})


def final_text(state: dict) -> str:
    content = state["messages"][-1].content
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)


def structured_output(state: dict):
    return state.get("structured_response")


def tool_outputs(state: dict) -> list[str]:
    """Tudo o que as tools devolveram (vira a base da checagem de números)."""
    return [str(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]
