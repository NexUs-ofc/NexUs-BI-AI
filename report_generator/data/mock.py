"""Dados mockados, determinísticos por mês, no formato das tabelas do NexUs-db.

O mesmo (ano, mês) sempre gera os mesmos dados. Há uma tendência leve de melhora no desperdício ao longo
dos meses e uma UF pequena (abaixo do mínimo de privacidade) para exercitar a supressão.

Teste rápido:  python -m report_generator.data.mock 2026 10
"""
import sys
from datetime import timedelta

import numpy as np
import pandas as pd

from report_generator.config import MOCK_SEED
from report_generator.data.loader import MonthData, last_day

# Categorias do NexUs-db (seed.py) com vida útil típica em dias (min, max)
CATEGORIES = {
    "Açúcares e Adoçantes": (180, 720),
    "Bebidas": (30, 365),
    "Biscoitos e Snacks": (60, 240),
    "Carnes, Aves e Pescados": (2, 10),
    "Cereais e Grãos": (180, 540),
    "Congelados": (60, 240),
    "Conservas e Enlatados": (365, 900),
    "Doces e Sobremesas": (15, 180),
    "Farinhas, Fermentos e Misturas": (90, 360),
    "Frutas, Verduras e Legumes": (3, 14),
    "Laticínios e Ovos": (5, 30),
    "Massas": (180, 540),
    "Molhos, Condimentos e Temperos": (90, 540),
    "Óleos e Gorduras": (180, 540),
    "Padaria": (3, 10),
    "Pratos Prontos": (2, 7),
    "Outros": (30, 365),
}

FOODS = [
    ("Açúcar refinado", "Açúcares e Adoçantes"), ("Adoçante", "Açúcares e Adoçantes"),
    ("Refrigerante", "Bebidas"), ("Suco de uva", "Bebidas"), ("Cerveja", "Bebidas"),
    ("Biscoito recheado", "Biscoitos e Snacks"), ("Batata chips", "Biscoitos e Snacks"),
    ("Frango", "Carnes, Aves e Pescados"), ("Carne moída", "Carnes, Aves e Pescados"),
    ("Picanha", "Carnes, Aves e Pescados"), ("Arroz", "Cereais e Grãos"), ("Feijão", "Cereais e Grãos"),
    ("Aveia", "Cereais e Grãos"), ("Pizza congelada", "Congelados"), ("Hambúrguer congelado", "Congelados"),
    ("Milho em lata", "Conservas e Enlatados"), ("Atum em lata", "Conservas e Enlatados"),
    ("Doce de leite", "Doces e Sobremesas"), ("Chocolate", "Doces e Sobremesas"),
    ("Farinha de trigo", "Farinhas, Fermentos e Misturas"), ("Fermento", "Farinhas, Fermentos e Misturas"),
    ("Banana", "Frutas, Verduras e Legumes"), ("Tomate", "Frutas, Verduras e Legumes"),
    ("Alface", "Frutas, Verduras e Legumes"), ("Maçã", "Frutas, Verduras e Legumes"),
    ("Leite", "Laticínios e Ovos"), ("Iogurte", "Laticínios e Ovos"), ("Queijo muçarela", "Laticínios e Ovos"),
    ("Ovos", "Laticínios e Ovos"), ("Macarrão", "Massas"), ("Lasanha", "Massas"),
    ("Molho de tomate", "Molhos, Condimentos e Temperos"), ("Sal", "Molhos, Condimentos e Temperos"),
    ("Óleo de soja", "Óleos e Gorduras"), ("Manteiga", "Óleos e Gorduras"),
    ("Pão francês", "Padaria"), ("Pão de forma", "Padaria"),
    ("Marmita pronta", "Pratos Prontos"), ("Salada pronta", "Pratos Prontos"), ("Ração", "Outros"),
]

# UF -> nº de households. AC fica abaixo do mínimo de privacidade (10) de propósito.
UFS = {"SP": 70, "RJ": 40, "MG": 35, "RS": 22, "PR": 20, "BA": 25, "PE": 18, "CE": 15,
       "GO": 14, "DF": 12, "SC": 16, "AM": 11, "AC": 4}

# Probabilidade de desperdício por categoria (perecíveis desperdiçam mais)
WASTE_BIAS = {"Frutas, Verduras e Legumes": 2.2, "Padaria": 2.0, "Laticínios e Ovos": 1.6,
              "Pratos Prontos": 1.8, "Carnes, Aves e Pescados": 1.4}


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [{"food_id": i + 1, "alimento": name, "categoria": cat} for i, (name, cat) in enumerate(FOODS)]
    )


def _households() -> pd.DataFrame:
    rows, hid = [], 1
    for uf, n in UFS.items():
        for _ in range(n):
            rows.append({"household_id": hid, "uf": uf})
            hid += 1
    return pd.DataFrame(rows)


def build_month(ano: int, mes: int) -> MonthData:
    rng = np.random.default_rng(MOCK_SEED * 10_000 + ano * 100 + mes)
    ref = last_day(ano, mes)
    month_index = (ano - 2025) * 12 + mes  # tendência suave ao longo do tempo
    catalog = _catalog()
    households = _households()
    # Perecíveis aparecem menos nas despensas do que secos e enlatados
    weights = catalog["categoria"].map(lambda c: 0.25 if CATEGORIES[c][1] <= 30 else 1.0)

    # Perfil de cada household: algumas desperdiçam bem mais (cauda), e o geral melhora devagar
    hh_waste = rng.gamma(2.0, 0.5, len(households))
    base_waste = max(0.06, 0.24 - 0.004 * month_index)
    expired_share = max(0.02, 0.065 - 0.001 * month_index)
    null_share = 0.03 + 0.02 * rng.random()

    items, events, settings = [], [], []
    for (hid, uf), w in zip(households[["household_id", "uf"]].itertuples(index=False), hh_waste, strict=True):
        foods = catalog.sample(int(rng.integers(6, 16)), weights=weights, random_state=int(rng.integers(1 << 31)))
        for f in foods.itertuples(index=False):
            lo, hi = CATEGORIES[f.categoria]
            shelf = int(rng.integers(lo, hi + 1))
            if rng.random() < null_share:
                expiry, created = pd.NaT, ref - timedelta(days=int(rng.integers(0, 60)))
            else:
                if rng.random() < expired_share * min(w, 3):
                    offset = -int(rng.integers(1, 31))  # já venceu e continua na despensa
                else:
                    offset = int(rng.integers(0, max(shelf, 1) + 1))
                expiry = ref + timedelta(days=offset)
                created = expiry - timedelta(days=shelf)
                created = min(created, ref)
            items.append({"household_id": hid, "uf": uf, "food_id": f.food_id, "alimento": f.alimento,
                          "categoria": f.categoria, "quantity": int(rng.integers(1, 8)),
                          "expiry_date": expiry, "created_at": created})

        # Eventos do mês (records): consumidos x vencidos
        for _ in range(int(rng.poisson(9))):
            f = foods.iloc[int(rng.integers(len(foods)))]
            p = min(0.9, base_waste * w * WASTE_BIAS.get(f.categoria, 0.7))
            day = int(rng.integers(1, ref.day + 1))
            events.append({"household_id": hid, "uf": uf, "food_id": f.food_id, "alimento": f.alimento,
                           "categoria": f.categoria,
                           "event_type": "item_expired" if rng.random() < p else "item_consumed",
                           "date": ref.replace(day=day), "discarded_quantity": int(rng.integers(1, 5))})

        # Mínimos configurados (~65% dos households). Alguns com mínimo 0 (= não configurado).
        if rng.random() < 0.65:
            qty = {r["food_id"]: r["quantity"] for r in items if r["household_id"] == hid}
            for f in foods.sample(min(len(foods), int(rng.integers(2, 5))),
                                  random_state=int(rng.integers(1 << 31))).itertuples(index=False):
                have = qty.get(f.food_id, 0)
                r = rng.random()
                minimum = 0 if r < 0.1 else (have + int(rng.integers(1, 4)) if r < 0.17 else max(1, have - 1))
                settings.append({"household_id": hid, "food_id": f.food_id, "alimento": f.alimento,
                                 "categoria": f.categoria, "minimum_quantity": minimum})

    items_df = pd.DataFrame(items)
    items_df["expiry_date"] = pd.to_datetime(items_df["expiry_date"])
    items_df["created_at"] = pd.to_datetime(items_df["created_at"])
    events_df = pd.DataFrame(events)
    events_df["date"] = pd.to_datetime(events_df["date"])
    return MonthData(ano=ano, mes=mes, data_referencia=ref, households=households, items=items_df,
                     events=events_df, settings=pd.DataFrame(settings), fonte="mock")


if __name__ == "__main__":
    a, m = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2026, 10)
    d = build_month(a, m)
    print(f"{m:02d}/{a}: {len(d.households)} households, {len(d.items)} itens, "
          f"{len(d.events)} eventos, {len(d.settings)} mínimos")
    print(d.items.head())
