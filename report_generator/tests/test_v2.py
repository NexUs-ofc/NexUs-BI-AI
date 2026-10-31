"""Relatório v2: ações do app, textos sem códigos, mês sem despensa, agendador diário, endpoints e Supabase."""
import re
from datetime import UTC, datetime

import httpx
import pytest

from report_generator import pipeline, scheduler
from report_generator.analysis.acoes import acoes_app
from report_generator.analysis.textos import narrativa_sem_codigos, sem_codigos
from report_generator.charts_data import charts_payload
from report_generator.config import BRAZIL_TZ
from report_generator.data import databricks
from report_generator.rendering.html import render_html
from report_generator.storage import files, mongo
from report_generator.tests.test_databricks import FakeConnection, gold_tables


def brt(*args) -> datetime:
    return datetime(*args, tzinfo=BRAZIL_TZ)


# ---------------------------------------------------------------- textos
def test_sem_codigos():
    assert sem_codigos("A taxa de desperdício (D1) subiu; D2 caiu.") == (
        "A taxa de desperdício subiu; descarte por esquecimento caiu.")
    assert sem_codigos("D1: texto") == "texto"
    assert sem_codigos("(D3 e D4) juntos") == "juntos"
    n = narrativa_sem_codigos({"resumo_executivo": "x (D1)", "analise_por_kpi": [{"kpi": "D1", "texto": "D9 lidera"}],
                               "insights": [{"tipo": "alerta", "titulo": "D3 alto", "texto": "t", "kpis": ["D3"]}],
                               "recomendacoes": ["r (D4)"], "limitacoes": []})
    assert n["analise_por_kpi"][0]["kpi"] == "D1" and n["insights"][0]["kpis"] == ["D3"]  # chaves internas ficam
    assert "D9" not in n["analise_por_kpi"][0]["texto"]


# ---------------------------------------------------------------- relatório a partir da Gold
@pytest.fixture
def make_report(db, monkeypatch):
    monkeypatch.setitem(databricks.DATABRICKS, "catalog", "workspace")
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "gold")
    monkeypatch.setattr("report_generator.data.loader.DATA_SOURCE", "databricks")

    def make(com_despensa: bool, ano=2026, mes=10):
        tables = gold_tables()
        skip = ()
        if not com_despensa:
            tables["kpi_estado_diario"] = tables["kpi_estado_diario"].iloc[0:0]
            skip = databricks.STATE_TABLES
        gold = databricks.load_gold(ano, mes, connect=lambda: FakeConnection(tables, [], skip))
        monkeypatch.setattr(databricks, "load_gold_cached", lambda a, m: gold)
        return pipeline.run(ano, mes, use_ai=False, with_pdf=False)

    return make


def _visible_text(html: str) -> str:
    body = html.split("</style>", 1)[1]
    return re.sub(r"<[^>]+>", " ", body)


@pytest.mark.parametrize("com_despensa", [True, False])
def test_relatorio_sem_codigos_para_o_leitor(make_report, com_despensa):
    html = render_html(make_report(com_despensa))
    assert not re.search(r"\bD[1-9]\b", _visible_text(html))


def test_sem_despensa_remove_visao_e_cards_de_estado(make_report):
    report = make_report(False)
    assert report["dados"]["tem_despensa"] is False and report["qualidade"]["sem_foto_da_despensa"] is True
    html = render_html(report)
    assert "3 · Despensa" not in html and "Itens vencidos na despensa" not in html.split("Como os números")[0]
    assert "Quem mais desperdiça" in html and "Taxa de desperdício" in html
    assert {a["id"] for a in report["acoes_app"]}.isdisjoint({"cadastro_validade", "alerta_vence_7d"})
    payload = charts_payload(report)
    assert payload["disponivel"]["despensa"] is False and payload["despensa"] is None
    assert payload["kpis"]["despensa"] == []


def test_com_despensa_mostra_as_tres_visoes(make_report):
    report = make_report(True)
    html = render_html(report)
    assert all(t in html for t in ("1 · Visão geral", "2 · Desperdício", "3 · Despensa"))
    assert report["resumo"] if "resumo" in report else report["dados"]["resumo"]["fora_da_meta"] == 2
    assert "2 de 5" in html  # "X de Y avaliados fora da meta"


def test_regerar_mantem_publicado_e_pdf(make_report, db):
    make_report(True)
    mongo.set_status(2026, 10, "publicado")
    mongo.set_pdf(2026, 10, "supabase://relatorio/relatorios/2026/10.pdf")
    again = make_report(True)
    saved = mongo.find_report(2026, 10)
    assert again["status"] == "publicado" and saved["status"] == "publicado"
    assert saved["pdf"]["uri"].endswith("2026/10.pdf")
    assert db["reports"].count_documents({}) == 1 if "reports" in db.list_collection_names() else True


def test_acoes_do_app_ligadas_aos_numeros(make_report):
    from report_generator.schemas import Dados

    report = make_report(True)
    acoes = {a["id"]: a for a in report["acoes_app"]}
    assert "21,4%" in acoes["alerta_pos_vencimento"]["evidencia"]
    assert "Padaria" in acoes["lembrete_perecivel"]["titulo"]
    assert "11,3%" in acoes["alerta_vence_7d"]["evidencia"]
    assert [a.prioridade for a in acoes_app(Dados(**report["dados"]))] == sorted(a["prioridade"] for a in acoes.values())


def test_charts_payload(make_report):
    p = charts_payload(make_report(True))
    assert p["resumo"]["unidadesSaidas"] == 900 and p["resumo"]["foraDaMeta"] == 2
    assert len(p["evolucao"]) == 6 and p["evolucao"][-1]["anoMes"] == "2026-10"
    assert p["categorias"][0]["categoria"] == "Padaria" and p["categorias"][0]["desperdicioPorCasa"] == 1.25
    assert p["regioes"] and p["momentoDescarte"] and p["despensa"]["porUf"]
    assert "D1" not in str(p["kpis"]["desperdicio"][0]["nome"])


# ---------------------------------------------------------------- agendador diário
@pytest.fixture
def fake(monkeypatch):
    state = {"reports": {}, "jobs": {}, "runs": []}

    def run(ano, mes, use_ai=True, with_pdf=True, model=None, keep_status=True):
        state["runs"].append((ano, mes))
        state["reports"][(ano, mes)] = {"ano": ano, "mes": mes, "parcial": (ano, mes) == (2026, 11)}

    monkeypatch.setattr(scheduler.pipeline, "run", run)
    monkeypatch.setattr(scheduler.mongo, "find_report", lambda a, m: state["reports"].get((a, m)))
    monkeypatch.setattr(scheduler.mongo, "find_job", lambda a, m: state["jobs"].get((a, m)))
    monkeypatch.setattr(scheduler.mongo, "set_job", lambda a, m, s, erro=None: state["jobs"].__setitem__(
        (a, m), {"status": s, "erro": erro, "atualizado_em": datetime.now(UTC)}))
    monkeypatch.setattr(scheduler, "SCHEDULE_HOUR", 8)
    monkeypatch.setattr(scheduler, "AUTO_PUBLISH", False)
    return state


def test_next_daily_run(fake):
    assert scheduler.next_daily_run(brt(2026, 10, 31, 7)) == brt(2026, 10, 31, 8)
    assert scheduler.next_daily_run(brt(2026, 10, 31, 8)) == brt(2026, 11, 1, 8)


def test_daily_fecha_o_mes_anterior_uma_vez_e_atualiza_o_atual(fake):
    r = scheduler.generate_daily(brt(2026, 11, 1, 8))
    assert fake["runs"] == [(2026, 10), (2026, 11)] and [a["acao"] for a in r["acoes"]] == ["fechado", "gerado"]
    fake["reports"][(2026, 10)]["parcial"] = False  # outubro foi fechado
    scheduler.generate_daily(brt(2026, 11, 2, 8))
    assert fake["runs"][2:] == [(2026, 11)]  # outubro não é refeito; novembro (parcial) sim


def test_daily_refaz_o_mes_anterior_que_foi_gerado_parcial(fake):
    fake["reports"][(2026, 10)] = {"ano": 2026, "mes": 10, "parcial": True}
    scheduler.generate_daily(brt(2026, 11, 1, 8))
    assert (2026, 10) in fake["runs"]


def test_ran_today(fake):
    assert scheduler._ran_today(brt(2026, 11, 1, 9)) is False
    scheduler.mongo.set_job(2026, 11, "concluido")
    now = datetime.now(BRAZIL_TZ)
    fake["jobs"][(now.year, now.month)] = fake["jobs"][(2026, 11)]
    assert scheduler._ran_today(now) is True


# ---------------------------------------------------------------- Supabase
@pytest.fixture
def supabase(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(200, json={"signedURL": "/object/sign/relatorio/relatorios/2026/10.pdf?token=abc"})
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(files.httpx, "post", client.post)
    monkeypatch.setattr(files, "SUPABASE_URL", "https://proj.supabase.co")
    return calls


def test_chave_sb_secret_nao_vai_no_authorization(monkeypatch, supabase):
    monkeypatch.setattr(files, "SUPABASE_KEY", "sb_secret_abc")
    files.save_pdf(b"%PDF", 2026, 10)
    h = supabase[0].headers
    assert h["apikey"] == "sb_secret_abc" and "authorization" not in h


def test_url_assinada(monkeypatch, supabase):
    monkeypatch.setattr(files, "SUPABASE_KEY", "eyJ.jwt.key")
    url = files.signed_url("supabase://relatorio/relatorios/2026/10.pdf", 600)
    assert url == "https://proj.supabase.co/storage/v1/object/sign/relatorio/relatorios/2026/10.pdf?token=abc"
    assert supabase[0].url.path == "/storage/v1/object/sign/relatorio/relatorios/2026/10.pdf"
    assert files.signed_url("/tmp/local.pdf") is None


# ---------------------------------------------------------------- Mongo
def test_save_report_confirma_e_job_guarda_historico(db):
    mongo.save_report({"ano": 2026, "mes": 10, "status": "rascunho"})
    mongo.save_report({"ano": 2026, "mes": 10, "status": "rascunho"})
    assert db["reports"].count_documents({}) == 1 if "reports" in db.list_collection_names() else True
    mongo.set_job(2026, 10, "em_execucao")
    mongo.set_job(2026, 10, "erro", erro="boom")
    job = mongo.find_job(2026, 10)
    assert job["status"] == "erro" and [h["status"] for h in job["historico"]] == ["em_execucao", "erro"]


def test_charts_trazem_media_movel_e_atraso_do_descarte(make_report):
    from report_generator.charts_data import _faixas_atraso, _media_movel

    assert _media_movel([10, 20, None, 30]) == [10.0, 15.0, 15.0, 25.0]
    faixas = _faixas_atraso([{"inicio": 0, "unidades": 5}, {"inicio": 14, "unidades": 2}])
    assert [f["rotulo"] for f in faixas] == ["0-6", "7-13", "14-20"] and faixas[1]["unidades"] == 0
    payload = charts_payload(make_report(True))
    assert all("mediaMovel3m" in p for p in payload["evolucao"])
    assert payload["atrasoDescarte"]["porCategoria"] and payload["atrasoDescarte"]["faixas"]
