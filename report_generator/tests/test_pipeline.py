"""Pipeline completo: sem IA, e com os agentes usando um modelo falso (sem chamar o Gemini)."""
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

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
    assert mongo.find_report(2026, 10)["status"] == "rascunho"
    assert "Outubro de 2026" in render_html(report)


class ScriptedModel(BaseChatModel):
    """Chat model falso: devolve as respostas da lista, em ordem."""

    responses: list
    index: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        message = self.responses[self.index]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


def _call(name: str, args: dict, i: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def test_pipeline_with_agents(db):
    pipeline.run(2026, 9, use_ai=False, with_pdf=False)
    narrativa = {
        "resumo_executivo": "Resumo do mês.",
        "analise_por_kpi": [{"kpi": "D1", "texto": "Texto do D1."}],
        "insights": [{"tipo": "tendencia", "titulo": "Título", "texto": "Texto.", "kpis": ["D1"]}],
        "recomendacoes": ["Recomendação."],
        "limitacoes": [],
    }
    model = ScriptedModel(responses=[
        _call("consultar_kpis", {}, 1), AIMessage(content="PANORAMA: ok\nD1: ok"),         # analista
        _call("historico_kpi", {"codigo": "D1"}, 2), AIMessage(content="INSIGHTS:\n- ok"),  # insights
        _call("Narrativa", narrativa, 3),                                                  # formalizador
    ])
    report = pipeline.run(2026, 10, use_ai=True, with_pdf=False, model=model)
    assert report["gerado_com_ia"] is True
    assert report["narrativa"]["resumo_executivo"] == "Resumo do mês."
    assert model.index == 5
