"""Acesso à base de dados (hoje um CSV). Trocar por Postgres/BigQuery depois mexe só aqui."""
from functools import lru_cache

import pandas as pd

from app.config import DATA_PATH


@lru_cache(maxsize=1)
def carregar_base() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Base de dados não encontrada em {DATA_PATH}")
    return pd.read_csv(DATA_PATH)


def nome_base() -> str:
    return DATA_PATH.name
