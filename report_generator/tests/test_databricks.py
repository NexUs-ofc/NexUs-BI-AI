"""Gold do Databricks com uma conexão falsa (sem warehouse): leitura, relatório e dashboard."""
from decimal import Decimal

import pandas as pd
import pytest

from report_generator.analysis.gold import gold_dashboard, gold_to_dados
from report_generator.data import databricks

D = Decimal


def gold_tables() -> dict[str, pd.DataFrame]:
    """Como o warehouse devolve: DECIMAL como Decimal e datas como date/texto.

    A ordem das chaves segue `build_queries()` (kpi_* na ordem declarada, depois as fato_* na ordem de
    `_fato_queries()`), porque `FakeCursor` devolve as tabelas na ordem em que `execute()` é chamado.
    """
    mensal = pd.DataFrame([
        {"ano_mes": f"2026-{m:02d}", "mes_completo": 1, "operacoes": 1000 + m, "unidades_descartadas": 100 + m,
         "unidades_movimentadas": 900, "d1_pct": D(f"{10 + m * 0.5:.2f}"), "d1_variacao_pp": D("0.50"),
         "d2_esquecidos_pct": D("21.37")} for m in range(1, 11)])
    estado = pd.DataFrame([{"data_referencia": "2026-10-31", "lotes": 5000, "unidades": 20000,
                            "d3_vencidos_pct": D("4.25"), "d4_vencem_7d_pct": D("11.30"),
                            "d8_sem_validade_pct": D("8.00"), "d7_vida_util_media": D("120.40"),
                            "d6_abaixo_minimo_pct": D("31.00"), "ano_mes": "2026-10", "ultimo_dia_do_mes": 1}])
    uf = pd.DataFrame([
        {"uf": "SP", "nome_uf": "São Paulo", "regiao": "Sudeste", "lotes": 900, "unidades": 4000,
         "unidades_em_risco": 600, "pct_em_risco": D("15.00"), "d3_vencidos_pct": D("5.00"),
         "d4_vencem_7d_pct": D("9.00"), "d8_sem_validade_pct": D("10.00"), "households_com_minimo": 50,
         "d6_abaixo_minimo_pct": D("30.00"), "unidades_movimentadas": 3000, "d1_pct": D("14.00")},
        {"uf": "BA", "nome_uf": "Bahia", "regiao": "Nordeste", "lotes": 300, "unidades": 1000,
         "unidades_em_risco": 250, "pct_em_risco": D("25.00"), "d3_vencidos_pct": D("8.00"),
         "d4_vencem_7d_pct": D("12.00"), "d8_sem_validade_pct": D("0.00"), "households_com_minimo": 20,
         "d6_abaixo_minimo_pct": D("40.00"), "unidades_movimentadas": 800, "d1_pct": D("19.00")},
        {"uf": "AC", "nome_uf": "Acre", "regiao": "Norte", "lotes": 12, "unidades": 40,
         "unidades_em_risco": 30, "pct_em_risco": D("75.00"), "d3_vencidos_pct": D("50.00"),
         "d4_vencem_7d_pct": D("20.00"), "d8_sem_validade_pct": D("0.00"), "households_com_minimo": 2,
         "d6_abaixo_minimo_pct": D("50.00"), "unidades_movimentadas": 20, "d1_pct": D("60.00")},
    ])
    cards = pd.DataFrame([{"codigo": "D1", "valor": D("15.00"), "data_referencia": "2026-10-31"}])

    evento_resumo = pd.DataFrame([{"unidades_saidas": D("900"), "unidades_descartadas": D("110"), "casas": 80,
                                   "operacoes": 1010}])
    evento_categoria = pd.DataFrame([
        {"categoria": "Padaria", "unidades_descartadas": D("50"), "unidades_saidas": D("300"), "casas": 40},
        {"categoria": "Bebidas", "unidades_descartadas": D("10"), "unidades_saidas": D("200"), "casas": 50},
        {"categoria": "Não informada", "unidades_descartadas": D("40"), "unidades_saidas": D("400"), "casas": 60},
    ])
    evento_regiao = pd.DataFrame([
        {"regiao": "Sudeste", "unidades_descartadas": D("60"), "unidades_saidas": D("600"),
         "descartadas_com_validade": D("50"), "esquecidas": D("10")},
        {"regiao": "Nordeste", "unidades_descartadas": D("20"), "unidades_saidas": D("100"),
         "descartadas_com_validade": D("20"), "esquecidas": D("8")},
    ])
    evento_momento = pd.DataFrame([
        {"momento": "3 · Esquecido (+7 dias após vencer)", "unidades": D("40")},
        {"momento": "1 · Antes de vencer", "unidades": D("40")},
        {"momento": "2 · Até 7 dias após vencer", "unidades": D("30")},
    ])
    regiao_categoria = pd.DataFrame([
        {"categoria": "Padaria", "regiao": "Sudeste", "descartadas": 50, "consumidas": 200},
        {"categoria": "Padaria", "regiao": "Nordeste", "descartadas": 20, "consumidas": 80},
        {"categoria": "Bebidas", "regiao": "Sudeste", "descartadas": 10, "consumidas": 90},
        {"categoria": "Não informada", "regiao": "Sudeste", "descartadas": 5, "consumidas": 5},
    ])
    estoque_categoria = pd.DataFrame([
        {"categoria": "Padaria", "lotes": 300, "unidades_com_validade": D("1000"), "unidades_7d": D("150"),
         "q1": D("5.0"), "mediana": D("10.0"), "q3": D("20.0"), "minimo": D("1.0"), "maximo": D("30.0")},
        {"categoria": "Bebidas", "lotes": 100, "unidades_com_validade": D("400"), "unidades_7d": D("40"),
         "q1": D("10.0"), "mediana": D("15.0"), "q3": D("25.0"), "minimo": D("2.0"), "maximo": D("40.0")},
        {"categoria": "Não informada", "lotes": 50, "unidades_com_validade": D("100"), "unidades_7d": D("5"),
         "q1": D("3.0"), "mediana": D("8.0"), "q3": D("18.0"), "minimo": D("0.0"), "maximo": D("20.0")},
    ])
    estoque_total = pd.DataFrame([{"households": 500, "lotes_com_validade": 1200, "q1": D("5.0"),
                                   "mediana": D("12.0"), "q3": D("22.0"), "minimo": D("0.0"), "maximo": D("35.0"),
                                   "outliers": 15}])
    vida_util_faixas = pd.DataFrame([{"faixa": f, "itens": i} for f, i in
                                     [("0-7", 300), ("8-14", 250), ("15-21", 200), ("22-28", 150),
                                      ("29-35", 100), ("36-mais", 200)]])
    abaixo_minimo = pd.DataFrame([
        {"alimento": "Arroz", "categoria": "Padaria", "households": 40, "faltam": D("120")},
        {"alimento": "Leite", "categoria": "Bebidas", "households": 25, "faltam": D("60")},
    ])
    return {"kpi_desperdicio_mensal": mensal, "kpi_estado_diario": estado, "kpi_uf": uf,
            "kpi_cards": cards, "evento_resumo": evento_resumo, "evento_categoria": evento_categoria,
            "evento_regiao": evento_regiao, "evento_momento": evento_momento, "regiao_categoria": regiao_categoria,
            "estoque_categoria": estoque_categoria, "estoque_total": estoque_total,
            "vida_util_faixas": vida_util_faixas, "abaixo_minimo": abaixo_minimo}


class FakeCursor:
    """Devolve as tabelas na ORDEM em que `execute()` é chamado (= ordem de `build_queries()`), já que as
    consultas fato_* não têm o nome da tabela-chave (ex.: "estoque_total") no SQL para casar por substring."""

    def __init__(self, tables, log, skip=()):
        self.tables, self.log = tables, log
        # tabelas de estado não são consultadas quando o mês não tem foto da despensa (load_gold as pula)
        self._order = iter(v for k, v in tables.items() if k not in skip)
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params):
        self.log.append((query, params))
        self.current = next(self._order)

    def fetchall_arrow(self):
        df = self.current
        return type("Arrow", (), {"to_pandas": lambda _self: df})()


class FakeConnection:
    def __init__(self, tables, log, skip=()):
        self.tables, self.log, self.skip = tables, log, skip

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return FakeCursor(self.tables, self.log, self.skip)


@pytest.fixture
def gold(monkeypatch):
    monkeypatch.setitem(databricks.DATABRICKS, "catalog", "workspace")
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "gold")
    log = []
    data = databricks.load_gold(2026, 10, connect=lambda: FakeConnection(gold_tables(), log))
    data.log = log
    return data


def test_queries_read_only_the_kpi_and_fato_tables(gold):
    q = databricks.build_queries(2026, 10)
    assert set(q) == {"kpi_desperdicio_mensal", "kpi_estado_diario", "kpi_uf", "kpi_cards",
                      "evento_resumo", "evento_categoria", "evento_regiao", "evento_momento",
                      "regiao_categoria", "estoque_categoria", "estoque_total", "vida_util_faixas",
                      "abaixo_minimo"}
    # KPIs de evento: filtrados pelo mês do evento em fato_movimento
    for name in ("evento_resumo", "evento_categoria", "evento_regiao", "evento_momento"):
        assert "`fato_movimento`" in q[name][0] and "m.ano_mes_evento = :ano_mes" in q[name][0]
        assert q[name][1] == {"ano_mes": "2026-10"}
    assert "FROM `workspace`.`gold`.`kpi_estado_diario` WHERE `ano_mes` = :ano_mes" in q["kpi_estado_diario"][0]
    assert q["kpi_desperdicio_mensal"][1] == {"ano_mes": "2026-10"}
    assert q["estoque_total"][1] == {"ano_mes": "2026-10"}
    assert "`fato_movimento`" in q["regiao_categoria"][0] and "`fato_estoque_minimo`" in q["abaixo_minimo"][0]
    assert len(gold.log) == 13 and gold.data_foto == "2026-10-31"
    assert gold.mensal["d1_pct"].dtype.kind == "f"  # Decimal -> número


def test_report_dados_from_gold(gold):
    previous = {"kpis": {"D3": {"valor": 5.0}}, "vida_util": {"mediana": 11.0}}
    dados = gold_to_dados(gold, previous)
    d1 = dados.kpis["D1"]
    assert d1.valor == 15.0 and d1.mes_anterior == 14.5 and d1.variacao_pp == 0.5 and d1.status == "dentro_meta"
    assert d1.numerador == 110 and d1.denominador == 900
    assert dados.kpis["D2"].valor == 21.4 and dados.kpis["D2"].status == "sem_meta"
    assert dados.kpis["D3"].valor == round(4.25, 1)
    assert dados.kpis["D3"].variacao_pp is not None
    assert dados.kpis["D4"].status == "alerta" and dados.kpis["D6"].status == "acima_da_meta"  # meta D6 = 30
    assert dados.kpis["D8"].status == "dentro_meta"  # 8% < meta 10%
    assert dados.base.itens_na_despensa == 20000 and dados.base.eventos_no_mes == 1010
    assert dados.base.households == 500
    assert dados.vida_util.media == 120.4 and dados.vida_util.mediana == 12.0 and dados.vida_util.p25 == 5.0
    assert dados.vida_util.outliers == 15 and dados.vida_util.mediana_mes_anterior == 11.0

    ufs = {u.uf: u for u in dados.por_uf}
    assert ufs["AC"].suprimido and ufs["AC"].d5_rank is None  # 12 lotes < 30
    assert ufs["BA"].d5_rank == 1 and ufs["SP"].d5_rank == 2  # ranking pelo % em risco
    sp = ufs["SP"]  # 4000 unid., 10% sem validade -> 3600 com validade; 5% vencidas -> 180
    assert (sp.itens_com_validade, sp.vencidos, sp.a_vencer_30d) == (3600, 180, 420)

    cats = {c.categoria: c for c in dados.por_categoria}
    assert list(cats) == ["Padaria", "Bebidas"]  # sem "Não informada"
    assert cats["Padaria"].itens_com_validade == 1000 and cats["Padaria"].d4_pct_a_vencer_7d == 15.0
    assert cats["Padaria"].households_com_categoria == 40 and cats["Padaria"].d9_indice_desperdicio == 1.25

    # --- KPIs de evento do mês
    assert dados.tem_despensa and dados.data_foto_despensa == "2026-10-31"
    r = dados.resumo
    assert (r.unidades_saidas, r.unidades_descartadas, r.casas_com_movimento) == (900, 110, 80)
    assert r.avaliados == 5 and r.fora_da_meta == 2  # D4 (alerta) e D6 fora; D1, D3, D8 dentro
    assert len(dados.evolucao) == 6 and dados.evolucao[-1].ano_mes == "2026-10" and dados.evolucao[0].ano_mes == "2026-05"
    # D9 mensal = descartadas da categoria no mês ÷ casas que a movimentaram no mês
    cat = {c.categoria: c for c in dados.desperdicio_categoria}
    assert list(cat) == ["Padaria", "Bebidas"]
    assert cat["Padaria"].d9_indice == 1.25 and cat["Padaria"].d1_pct == 16.7 and cat["Padaria"].casas == 40
    assert cat["Padaria"].pct_do_desperdicio == 50.0  # 50 de 100 descartadas (incl. "Não informada")
    reg = {g.regiao: g for g in dados.desperdicio_regiao}
    assert reg["Sudeste"].d1_pct == 10.0 and reg["Sudeste"].d2_pct == 20.0
    assert reg["Nordeste"].d1_pct == 20.0 and reg["Nordeste"].d2_pct == 40.0
    assert [m.momento for m in dados.momento_descarte] == [
        "Antes de vencer", "Até 7 dias depois de vencer", "Esquecido (mais de 7 dias depois)"]
    assert dados.momento_descarte[0].pct == round(100 * 40 / 110, 1)

    minimo = {a.alimento: a for a in dados.top_abaixo_minimo}
    assert minimo["Arroz"].households == 40 and minimo["Leite"].categoria == "Bebidas"


def test_dashboard_from_gold(gold):
    d = gold_dashboard(gold)
    assert d["summary"] == {"wasteRate": 15.0, "expiredKg": 782, "expiringInSevenDaysKg": 2079,
                            "withoutExpiryKg": 1600}
    assert [p["id"] for p in d["monthlyWaste"]][-1] == "2026-10" and len(d["monthlyWaste"]) == 10
    assert {s["id"] for s in d["stateWaste"]} == {"SP", "BA"}  # AC fora (amostra pequena)
    assert {s["id"]: s["level"] for s in d["stateWaste"]}["BA"] == "highest"
    assert [r["id"] for r in d["regions"]] == ["nordeste", "sudeste"]
    assert "semDadosNaGold" not in d["meta"]

    cat_ids = {c["id"] for c in d["categories"]}
    assert cat_ids == {"padaria", "bebidas"}  # "Não informada" fora
    waste = {(c["regionId"], c["categoryId"]): c["volume"] for c in d["regionalWaste"]}
    assert waste[("sudeste", "padaria")] == 50 and waste[("nordeste", "padaria")] == 20
    consumption = {(c["regionId"], c["categoryId"]): c["kilograms"] for c in d["regionalConsumption"]}
    assert consumption[("sudeste", "bebidas")] == 90
    dist = {b["id"]: b["count"] for b in d["shelfLifeDistribution"]}
    assert dist["0-7"] == 300 and dist["36-mais"] == 200
    box = {b["categoryId"]: b for b in d["categoryShelfLife"]}
    assert box["padaria"]["median"] == 10.0 and box["padaria"]["thirdQuartile"] == 20.0
    below = {b["name"]: b["missingVolume"] for b in d["belowMinimum"]}
    assert below["Arroz"] == 120 and below["Leite"] == 60


def test_mes_sem_foto_da_despensa_so_tem_indicadores_de_evento(monkeypatch):
    """Setembro: há consumo/descarte (fato_movimento) mas nenhuma foto da despensa. Os indicadores de estado
    NÃO podem aparecer (nem a foto de hoje com rótulo de setembro) e as consultas de estado nem são enviadas."""
    monkeypatch.setitem(databricks.DATABRICKS, "catalog", "workspace")
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "gold")
    tables = gold_tables()
    tables["kpi_desperdicio_mensal"] = tables["kpi_desperdicio_mensal"][
        tables["kpi_desperdicio_mensal"]["ano_mes"] <= "2026-09"]
    tables["kpi_estado_diario"] = tables["kpi_estado_diario"].iloc[0:0]  # setembro: sem foto
    log = []
    gold_set = databricks.load_gold(2026, 9, connect=lambda: FakeConnection(tables, log, databricks.STATE_TABLES))
    # 2 kpi (mensal + estado) + 4 de evento + regiao_categoria = 7: as 6 de estado foram poupadas
    assert len(log) == 7
    assert gold_set.uf.empty and gold_set.data_foto is None

    dados = gold_to_dados(gold_set)
    assert dados.tem_despensa is False and dados.data_foto_despensa is None
    assert dados.por_uf == [] and dados.top_abaixo_minimo == []
    assert all(dados.kpis[c].valor is None and dados.kpis[c].status == "sem_dados" for c in ("D3", "D4", "D6", "D8"))
    assert dados.kpis["D1"].valor is not None and dados.desperdicio_categoria  # evento continua
    assert all(c.d4_pct_a_vencer_7d is None for c in dados.por_categoria)
    assert dados.resumo.avaliados == 1  # só a taxa de desperdício tem meta e valor

    d = gold_dashboard(gold_set)
    assert d["stateWaste"] == []


def test_foto_de_outro_mes_nao_vira_uf_do_mes_pedido(monkeypatch):
    """kpi_uf só guarda a foto de hoje (31/10). Pedindo setembro COM foto de setembro, a UF de hoje não pode
    aparecer com rótulo de setembro."""
    monkeypatch.setitem(databricks.DATABRICKS, "catalog", "workspace")
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "gold")
    tables = gold_tables()
    tables["kpi_estado_diario"] = tables["kpi_estado_diario"].assign(data_referencia="2026-09-30", ano_mes="2026-09")
    gold_set = databricks.load_gold(2026, 9, connect=lambda: FakeConnection(tables, []))
    dados = gold_to_dados(gold_set)
    assert dados.tem_despensa and dados.por_uf == []  # data_foto (kpi_cards) é de outubro


def test_missing_column_is_reported(monkeypatch):
    tables = gold_tables()
    tables["kpi_uf"] = tables["kpi_uf"].drop(columns=["pct_em_risco"])
    with pytest.raises(ValueError, match="pct_em_risco"):
        databricks.load_gold(2026, 10, connect=lambda: FakeConnection(tables, []))


def test_rejects_unsafe_names(monkeypatch):
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "x; DROP TABLE y")
    with pytest.raises(ValueError, match="Nome inválido"):
        databricks.table_name("kpi_uf")


def test_loader_switches_source(monkeypatch, gold):
    from report_generator.data import loader

    monkeypatch.setattr(databricks, "load_gold_cached", lambda ano, mes: gold)
    dados, fonte = loader.load_dados(2026, 10, source="databricks")
    assert fonte == "databricks" and dados.kpis["D1"].valor == 15.0
    assert loader.load_dados(2026, 10, source="mock")[1] == "mock"
    with pytest.raises(ValueError):
        loader.load_dados(2026, 10, source="excel")


def test_full_report_from_gold_renders(db, monkeypatch, gold):
    """Relatório inteiro só com a Gold: narrativa sem IA, checagem de números e HTML."""
    from report_generator import pipeline
    from report_generator.rendering.html import render_html

    monkeypatch.setattr(databricks, "load_gold_cached", lambda ano, mes: gold)
    monkeypatch.setattr("report_generator.data.loader.DATA_SOURCE", "databricks")
    report = pipeline.run(2026, 10, use_ai=False, with_pdf=False)
    assert report["fonte_dados"] == "databricks"
    assert report["qualidade"]["numeros_sem_fonte"] == []
    html = render_html(report)
    assert "Outubro de 2026" in html and "Arroz" in html  # top_abaixo_minimo vindo da fato_estoque_minimo
    assert "BA" in html and "25,0%" in html  # D5 % em risco na tabela de UFs
    assert "3 · Despensa" in html and "Quem mais desperdiça" in html
    assert report["acoes_app"] and {a["id"] for a in report["acoes_app"]} >= {"alerta_pos_vencimento",
                                                                             "lembrete_perecivel"}


def test_cache_reuses_the_same_month(monkeypatch):
    """Relatório diário e /dashboard pedem o mesmo mês: o warehouse só é consultado uma vez."""
    monkeypatch.setitem(databricks.DATABRICKS, "catalog", "workspace")
    monkeypatch.setitem(databricks.DATABRICKS, "schema", "gold")
    log = []
    connect = lambda: FakeConnection(gold_tables(), log)
    first = databricks.load_gold_cached(2026, 10, ttl=60, connect=connect)
    again = databricks.load_gold_cached(2026, 10, ttl=60, connect=connect)
    assert first is again and len(log) == 13
    databricks.load_gold_cached(2026, 9, ttl=60, connect=connect)
    assert len(log) == 26  # outro mês = outra leitura
