"""Fórmulas dos KPIs conferidas com dados pequenos, montados à mão."""
from datetime import date

import pandas as pd

from report_generator.analysis.descriptive import build_dados
from report_generator.data.loader import MonthData

REF = date(2026, 10, 31)


def _month(n_households_ac: int = 2) -> MonthData:
    hh = [{"household_id": i, "uf": "SP"} for i in range(1, 11)]
    hh += [{"household_id": 100 + i, "uf": "AC"} for i in range(n_households_ac)]

    def item(h, food, cat, days, qty=1, null=False):
        exp = pd.NaT if null else pd.Timestamp(REF) + pd.Timedelta(days=days)
        created = pd.Timestamp(REF) - pd.Timedelta(days=10)
        return {"household_id": h, "uf": "SP" if h < 100 else "AC", "food_id": food, "alimento": f"a{food}",
                "categoria": cat, "quantity": qty, "expiry_date": exp, "created_at": created}

    items = [
        item(1, 1, "Padaria", -2),   # vencido
        item(2, 1, "Padaria", 3),    # vence em 7 dias
        item(3, 2, "Massas", 100),
        item(4, 2, "Massas", 20),    # vence em 30 dias
        item(5, 2, "Massas", 0, null=True),  # sem validade
        item(101, 1, "Padaria", -1),  # AC (suprimido)
    ]
    events = [{"household_id": 1, "uf": "SP", "food_id": 1, "alimento": "a1", "categoria": "Padaria",
               "event_type": t, "date": pd.Timestamp(REF), "discarded_quantity": 1}
              for t in ["item_expired", "item_consumed", "item_consumed", "item_consumed"]]
    settings = [
        {"household_id": 1, "food_id": 1, "alimento": "a1", "categoria": "Padaria", "minimum_quantity": 5},  # abaixo
        {"household_id": 3, "food_id": 2, "alimento": "a2", "categoria": "Massas", "minimum_quantity": 1},  # ok
        {"household_id": 4, "food_id": 9, "alimento": "a9", "categoria": "Massas", "minimum_quantity": 0},  # ignora
    ]
    items_df = pd.DataFrame(items)
    items_df["expiry_date"] = pd.to_datetime(items_df["expiry_date"])
    return MonthData(ano=2026, mes=10, data_referencia=REF, households=pd.DataFrame(hh), items=items_df,
                     events=pd.DataFrame(events), settings=pd.DataFrame(settings), fonte="teste")


def test_card_kpis():
    d = build_dados(_month())
    assert d.kpis["D1"].valor == 25.0  # 1 vencido / 4 eventos
    assert d.kpis["D3"].valor == 40.0  # 2 vencidos / 5 com validade
    assert d.kpis["D4"].valor == 20.0  # 1 a vencer em 7d / 5
    assert d.kpis["D6"].valor == 50.0  # 1 de 2 households com mínimo > 0
    assert d.kpis["D8"].valor == round(100 / 6, 1)  # 1 sem validade / 6 itens
    assert d.kpis["D1"].status == "acima_da_meta"
    assert d.kpis["D4"].status == "alerta"


def test_variation_uses_previous_month():
    previous = {"kpis": {"D1": {"valor": 30.0}}}
    d = build_dados(_month(), previous)
    assert d.kpis["D1"].mes_anterior == 30.0
    assert d.kpis["D1"].variacao_pp == -5.0


def test_privacy_and_ranking():
    d = build_dados(_month())
    ac = next(u for u in d.por_uf if u.uf == "AC")
    sp = next(u for u in d.por_uf if u.uf == "SP")
    assert ac.suprimido and ac.vencidos is None and ac.d5_rank is None
    assert sp.d5_rank == 1 and sp.vencidos == 1 and sp.a_vencer_30d == 2


def test_category_index():
    d = build_dados(_month())
    padaria = next(c for c in d.por_categoria if c.categoria == "Padaria")
    assert padaria.expirados_no_mes == 1
    assert padaria.households_com_categoria == 3
    assert padaria.d9_indice_desperdicio == 0.33
    assert d.top_abaixo_minimo[0].alimento == "a1"
