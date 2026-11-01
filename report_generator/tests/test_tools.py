import json

from report_generator.agents.quality import known_numbers, unsupported_numbers
from report_generator.tools.calc_tools import comparar_com_meta, tendencia, variacao
from report_generator.tools.history_tools import build_history_tools


def test_calc_tools():
    assert json.loads(variacao(12.5, 15.0))["diferenca"] == -2.5
    t = json.loads(tendencia([17.0, 16.0, 15.0, 14.0]))
    assert t["direcao"] == "queda" and t["inclinacao_por_mes"] == -1.0 and t["meses_seguidos_no_mesmo_sentido"] == 3
    assert json.loads(comparar_com_meta("D1", 16.0))["status"] == "acima_da_meta"
    assert "erro" in json.loads(comparar_com_meta("D7", 1))


def test_history_tool_is_chronological():
    history = [  # como vem do Mongo: do mais recente para o mais antigo
        {"ano": 2026, "mes": 9, "dados": {"kpis": {"D1": {"valor": 14.0}}, "vida_util": {"mediana": 200}}},
        {"ano": 2026, "mes": 8, "dados": {"kpis": {"D1": {"valor": 15.0}}, "vida_util": {"mediana": 190}}},
    ]
    tool = {t.name: t for t in build_history_tools(2026, 10, history)}
    serie = json.loads(tool["historico_kpi"].invoke({"codigo": "D1"}))["serie"]
    assert [s["mes"] for s in serie] == ["08/2026", "09/2026"]
    assert "aviso" in json.loads(build_history_tools(2026, 10, [])[0].invoke({"codigo": "D1"}))


def test_quality_check():
    known = known_numbers({"a": 12.5, "b": 2758}, '{"c": 218.5}')
    narrativa = {"t": "Taxa de 12,5% em 2.758 eventos, mediana de 218 dias, em 2026; valor inventado 33,3%."}
    assert unsupported_numbers(narrativa, known) == ["33,3"]
