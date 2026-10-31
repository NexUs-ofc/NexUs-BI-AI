"""Pipeline completo: sem IA, e com os agentes usando um modelo falso (sem chamar o Gemini)."""
import asyncio

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from report_generator import pipeline
from report_generator.rendering.html import render_html
from report_generator.storage import mongo


def test_pipeline_without_ai_uses_history(db):
    for mes in (8, 9):
        pipeline.run(2026, mes, use_ai=False, with_pdf=False)
    report = pipeline.run(2026, 10, use_ai=False, with_pdf=False)

    assert report["qualidade"]["meses_de_historico"] == 2
    assert report["qualidade"]["numeros_sem_fonte"] == []
    d1 = report["dados"]["kpis"]["D1"]
    assert d1["mes_anterior"] == mongo.find_report(2026, 9)["dados"]["kpis"]["D1"]["valor"]
    assert mongo.find_report(2026, 10)["status"] == "publicado"
    assert "Outubro de 2026" in render_html(report)


ROLES = {"Você é o Analista Descritivo": "analista", "Você é o Cientista de Dados": "cientista",
         "Você é o Formalizador": "formalizador"}


class RoleModel(BaseChatModel):
    """Chat model falso: cada agente (pelo prompt de sistema) recebe as respostas do seu roteiro, em ordem.

    O analista e o cientista rodam ao mesmo tempo, então a ordem global das chamadas não é fixa; por
    isso o roteiro é por papel. `events` registra início/fim de cada chamada para conferir o paralelismo.
    """

    scripts: dict
    calls: dict = Field(default_factory=dict)
    events: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "role-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _role(self, messages) -> str:
        system = str(messages[0].content)
        return next(role for prefix, role in ROLES.items() if system.startswith(prefix))

    def _next(self, messages):
        role = self._role(messages)
        i = self.calls.get(role, 0)
        self.calls[role] = i + 1
        return role, ChatResult(generations=[ChatGeneration(message=self.scripts[role][i])])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._next(messages)[1]

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        role, result = self._next(messages)
        self.events.append(("inicio", role))
        await asyncio.sleep(0.05)  # simula a latência do Gemini
        self.events.append(("fim", role))
        return result


def _call(name: str, args: dict, i: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


NARRATIVA = {
    "resumo_executivo": "Resumo do mês.",
    "analise_por_kpi": [{"kpi": "D1", "texto": "Texto do D1."}],
    "insights": [{"tipo": "tendencia", "titulo": "Título", "texto": "Texto.", "kpis": ["D1"]}],
    "recomendacoes": ["Recomendação."],
    "limitacoes": [],
}


def _model() -> RoleModel:
    return RoleModel(scripts={
        "analista": [_call("consultar_kpis", {}, 1), AIMessage(content="PANORAMA: ok\nD1: ok")],
        "cientista": [_call("historico_kpi", {"codigo": "D1"}, 2), AIMessage(content="INSIGHTS:\n- ok")],
        "formalizador": [_call("Narrativa", NARRATIVA, 3)],
    })


def test_pipeline_with_agents(db):
    pipeline.run(2026, 9, use_ai=False, with_pdf=False)
    model = _model()
    report = pipeline.run(2026, 10, use_ai=True, with_pdf=False, model=model)
    assert report["gerado_com_ia"] is True
    assert report["narrativa"]["resumo_executivo"] == "Resumo do mês."
    assert model.calls == {"analista": 2, "cientista": 2, "formalizador": 1}


def test_analyst_and_data_scientist_run_in_parallel(db):
    model = _model()
    pipeline.run(2026, 10, use_ai=True, with_pdf=False, model=model)
    first_end = next(i for i, (kind, _) in enumerate(model.events) if kind == "fim")
    started_before = {role for kind, role in model.events[:first_end] if kind == "inicio"}
    assert started_before == {"analista", "cientista"}  # os dois começaram antes de qualquer um terminar
    assert model.events[-1] == ("fim", "formalizador")  # e o formalizador só roda depois dos dois
