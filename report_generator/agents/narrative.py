"""Os agentes do relatório.

    ┌─ analista descritivo ─┐   (em paralelo, asyncio.gather)
    │                       ├──> formalizador -> Narrativa (pydantic)
    └─ cientista de dados ──┘

1. analista          -> texto descritivo do mês              (tools de análise + cálculo)
2. cientista de dados -> tendências, alertas, recomendações   (tools de análise + cálculo + histórico)
3. formalizador       -> junta os dois textos na Narrativa estruturada, sem tools

O analista e o cientista leem os mesmos números pelas tools e não dependem um do outro, então rodam
ao mesmo tempo: a geração leva o tempo do mais lento, não a soma dos dois.
"""
import asyncio
from dataclasses import dataclass, field

from report_generator.agents.base import (
    arun_agent,
    build_agent,
    final_text,
    structured_output,
    tool_outputs,
)
from report_generator.agents.prompts.analyst import ANALYST_PROMPT, ANALYST_TASK
from report_generator.agents.prompts.data_scientist import (
    DATA_SCIENTIST_PROMPT,
    DATA_SCIENTIST_TASK,
)
from report_generator.agents.prompts.formalizer import (
    FORMALIZER_PROMPT,
    FORMALIZER_TASK,
)
from report_generator.schemas import Dados, Narrativa
from report_generator.tools.analysis_tools import build_analysis_tools
from report_generator.tools.calc_tools import build_calc_tools
from report_generator.tools.history_tools import build_history_tools

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro"]


def period_name(ano: int, mes: int) -> str:
    return f"{MONTHS[mes - 1]} de {ano}"


@dataclass
class NarrativeResult:
    narrativa: Narrativa
    textos: dict = field(default_factory=dict)  # saídas intermediárias (debug / auditoria)
    tool_outputs: list[str] = field(default_factory=list)


async def analyst_agent(dados: Dados, periodo: str, model=None) -> tuple[str, list[str]]:
    tools = [*build_analysis_tools(dados), *build_calc_tools()]
    state = await arun_agent(build_agent(ANALYST_PROMPT.format(periodo=periodo), tools, model=model),
                             ANALYST_TASK.format(periodo=periodo))
    return final_text(state), tool_outputs(state)


async def data_scientist_agent(dados: Dados, history: list[dict], ano: int, mes: int, periodo: str,
                               model=None) -> tuple[str, list[str]]:
    tools = [*build_analysis_tools(dados), *build_calc_tools(), *build_history_tools(ano, mes, history)]
    state = await arun_agent(build_agent(DATA_SCIENTIST_PROMPT.format(periodo=periodo), tools, model=model),
                             DATA_SCIENTIST_TASK.format(periodo=periodo))
    return final_text(state), tool_outputs(state)


async def formalizer_agent(analise: str, insights: str, periodo: str, model=None) -> Narrativa:
    agent = build_agent(FORMALIZER_PROMPT.format(periodo=periodo), response_format=Narrativa, model=model)
    state = await arun_agent(agent, FORMALIZER_TASK.format(periodo=periodo, analise=analise, insights=insights))
    narrativa = structured_output(state)
    if narrativa is None:
        raise RuntimeError("O formalizador não devolveu a narrativa no formato esperado.")
    return narrativa


async def agenerate_narrative(dados: Dados, history: list[dict], ano: int, mes: int,
                              model=None) -> NarrativeResult:
    periodo = period_name(ano, mes)
    (analise, out1), (insights, out2) = await asyncio.gather(
        analyst_agent(dados, periodo, model),
        data_scientist_agent(dados, history, ano, mes, periodo, model),
    )
    narrativa = await formalizer_agent(analise, insights, periodo, model)
    return NarrativeResult(narrativa=narrativa, textos={"analise": analise, "insights": insights},
                           tool_outputs=[*out1, *out2])


def generate_narrative(dados: Dados, history: list[dict], ano: int, mes: int, model=None) -> NarrativeResult:
    """Versão síncrona, para o pipeline. Ele sempre roda fora do event loop da API (thread da
    BackgroundTasks, asyncio.to_thread do agendador ou CLI), então asyncio.run é seguro aqui."""
    return asyncio.run(agenerate_narrative(dados, history, ano, mes, model=model))
