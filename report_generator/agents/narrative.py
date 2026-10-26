"""Os três agentes do relatório, em sequência:

1. analista    -> texto descritivo do mês      (tools de análise + cálculo)
2. insights    -> tendências, alertas, recomendações (tools de análise + cálculo + histórico do Mongo)
3. formalizador-> Narrativa estruturada (pydantic), sem tools
"""
from dataclasses import dataclass, field

from report_generator.agents.base import (
    build_agent,
    final_text,
    run_agent,
    structured_output,
    tool_outputs,
)
from report_generator.agents.prompts.analyst import ANALYST_PROMPT, ANALYST_TASK
from report_generator.agents.prompts.formalizer import (
    FORMALIZER_PROMPT,
    FORMALIZER_TASK,
)
from report_generator.agents.prompts.insights import INSIGHTS_PROMPT, INSIGHTS_TASK
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


def analyst_agent(dados: Dados, periodo: str, model=None) -> tuple[str, list[str]]:
    tools = [*build_analysis_tools(dados), *build_calc_tools()]
    state = run_agent(build_agent(ANALYST_PROMPT.format(periodo=periodo), tools, model=model),
                      ANALYST_TASK.format(periodo=periodo))
    return final_text(state), tool_outputs(state)


def insights_agent(dados: Dados, history: list[dict], ano: int, mes: int, analise: str, periodo: str,
                   model=None) -> tuple[str, list[str]]:
    tools = [*build_analysis_tools(dados), *build_calc_tools(), *build_history_tools(ano, mes, history)]
    state = run_agent(build_agent(INSIGHTS_PROMPT.format(periodo=periodo), tools, model=model),
                      INSIGHTS_TASK.format(periodo=periodo, analise=analise))
    return final_text(state), tool_outputs(state)


def formalizer_agent(analise: str, insights: str, periodo: str, model=None) -> Narrativa:
    state = run_agent(build_agent(FORMALIZER_PROMPT.format(periodo=periodo), response_format=Narrativa,
                                  model=model),
                      FORMALIZER_TASK.format(periodo=periodo, analise=analise, insights=insights))
    narrativa = structured_output(state)
    if narrativa is None:
        raise RuntimeError("O formalizador não devolveu a narrativa no formato esperado.")
    return narrativa


def generate_narrative(dados: Dados, history: list[dict], ano: int, mes: int, model=None) -> NarrativeResult:
    periodo = period_name(ano, mes)
    analise, out1 = analyst_agent(dados, periodo, model)
    insights, out2 = insights_agent(dados, history, ano, mes, analise, periodo, model)
    narrativa = formalizer_agent(analise, insights, periodo, model)
    return NarrativeResult(narrativa=narrativa, textos={"analise": analise, "insights": insights},
                           tool_outputs=[*out1, *out2])
