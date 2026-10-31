"""Fonte dos dados do mês. É o único lugar que sabe de onde os números vêm (REPORT_DATA_SOURCE):

- databricks:  camada Gold (data/databricks.py), com os KPIs oficiais já agregados -> analysis/gold.py
- mock:        linhas sintéticas e determinísticas (data/mock.py) -> analysis/descriptive.py (desenvolvimento
               e testes, sem warehouse)

O resto do código pede `load_dados` (bloco `dados` do relatório) ou `load_dashboard` (JSON do site) e não
precisa saber a fonte.

Colunas das linhas do mock (espelham o NexUs-db):
- households: household_id, uf
- items:      household_id, uf, food_id, alimento, categoria, quantity, expiry_date, created_at
- events:     household_id, uf, food_id, alimento, categoria, event_type, date, discarded_quantity
- settings:   household_id, food_id, alimento, categoria, minimum_quantity
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


def _source(source: str | None) -> str:
    source = source or DATA_SOURCE
    if source in ("databricks", "db"):  # "db" = nome antigo, mantido para não quebrar .env existentes
        return "databricks"
    if source == "mock":
        return "mock"
    raise ValueError(f"REPORT_DATA_SOURCE inválido: {source!r} (use 'mock' ou 'databricks').")


def load_month(ano: int, mes: int) -> MonthData:
    """Linhas do mock para um mês (a Gold não tem linhas: use load_dados / load_dashboard)."""
    from report_generator.data.mock import build_month

    return build_month(ano, mes)


def load_dados(ano: int, mes: int, previous: dict | None = None, source: str | None = None):
    """(bloco `dados` do relatório, nome da fonte). `previous` = `dados` do mês anterior, do Mongo."""
    if _source(source) == "databricks":
        from report_generator.analysis.gold import gold_to_dados
        from report_generator.data.databricks import load_gold_cached

        return gold_to_dados(load_gold_cached(ano, mes), previous), "databricks"
    from report_generator.analysis.descriptive import build_dados

    return build_dados(load_month(ano, mes), previous), "mock"


def load_dashboard(ano: int, mes: int, history_loader=list, source: str | None = None) -> dict:
    """JSON do Dashboard. `history_loader` (meses anteriores do Mongo) só é chamado no mock: na Gold a série
    mensal já vem de kpi_desperdicio_mensal."""
    if _source(source) == "databricks":
        from report_generator.analysis.gold import gold_dashboard
        from report_generator.data.databricks import load_gold_cached

        return gold_dashboard(load_gold_cached(ano, mes))
    from report_generator.analysis.dashboard import build_dashboard

    return build_dashboard(load_month(ano, mes), history_loader())
