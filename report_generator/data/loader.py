"""Carrega os dados de UM mês para a análise.

O resto do pipeline só conhece `MonthData`. Para trocar o mock pela base real, implemente
`_load_from_db` devolvendo os mesmos DataFrames, com as mesmas colunas, e mude REPORT_DATA_SOURCE=db.

Colunas (espelham o NexUs-db):
- households: household_id, uf                              (profile HOUSEHOLD + address.state)
- items:      household_id, uf, food_id, alimento, categoria, quantity, expiry_date, created_at
              -> foto da despensa (pantry_item) no ÚLTIMO dia do mês
- events:     household_id, uf, food_id, alimento, categoria, event_type, date, discarded_quantity
              -> eventos item_consumed / item_expired do mês (Mongo `records`)
- settings:   household_id, food_id, alimento, categoria, minimum_quantity  (pantry_product_setting)
"""
import calendar
from dataclasses import dataclass
from datetime import date

import pandas as pd

from report_generator.config import DATA_SOURCE


@dataclass
class MonthData:
    ano: int
    mes: int
    data_referencia: date
    households: pd.DataFrame
    items: pd.DataFrame
    events: pd.DataFrame
    settings: pd.DataFrame
    fonte: str


def last_day(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def load_month(ano: int, mes: int, source: str | None = None) -> MonthData:
    source = source or DATA_SOURCE
    if source == "mock":
        from report_generator.data.mock import build_month

        return build_month(ano, mes)
    if source == "db":
        return _load_from_db(ano, mes)
    raise ValueError(f"REPORT_DATA_SOURCE inválido: {source!r} (use 'mock' ou 'db').")


def _load_from_db(ano: int, mes: int) -> MonthData:
    raise NotImplementedError(
        "A leitura da base real ainda não existe. Ela depende da foto mensal da despensa "
        "(pantry_item não guarda histórico) e das views de BI do NexUs-db. Use REPORT_DATA_SOURCE=mock."
    )
