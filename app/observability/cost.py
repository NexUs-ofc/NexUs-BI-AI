"""Estimated cost of the Gemini calls.

Prices in US$ per 1 million tokens (Gemini API paid tier, prompts up to 200k tokens), checked in
10/2026. Google changes these values: check https://ai.google.dev/gemini-api/docs/pricing when needed.
The embeddings of the FAQ search are not counted (their cost is negligible here).

The dollar rate comes from the PTAX of Banco Central do Brasil (official rate, public API, no key),
the same source used by NexUs-AI. If the API is down, USD_TO_BRL_FALLBACK is used.
"""
import json
import urllib.request
from datetime import date, timedelta
from functools import lru_cache

from app.config import LLM_MODEL, today_in_brazil

# model -> (input price, output price) in US$ per 1M tokens
PRICES_USD_PER_1M_TOKENS = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
}

USD_TO_BRL_FALLBACK = 4.98  

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{day}'&$format=json"
)
PTAX_DAYS_BACK = 7  # weekends and holidays have no rate: look back up to a week
PTAX_TIMEOUT_SECONDS = 5


def _ptax_rate(day: date) -> float | None:
    """Selling rate of the day, or None if there is no rate that day."""
    url = PTAX_URL.format(day=day.strftime("%m-%d-%Y"))
    with urllib.request.urlopen(url, timeout=PTAX_TIMEOUT_SECONDS) as response:
        values = json.load(response).get("value", [])
    return float(values[0]["cotacaoVenda"]) if values else None


@lru_cache(maxsize=1)
def _usd_to_brl_of(today: date) -> tuple[float, str]:
    """Cached per day: the Banco Central is called at most once a day."""
    try:
        for days_back in range(PTAX_DAYS_BACK + 1):
            day = today - timedelta(days=days_back)
            rate = _ptax_rate(day)
            if rate:
                return rate, f"PTAX Banco Central {day.strftime('%d/%m/%Y')}"
    except Exception as e:  # noqa: BLE001 - offline, timeout, format change...
        print(f"[cost] ATENÇÃO: PTAX indisponível, usando cotação fixa: {e}")
    return USD_TO_BRL_FALLBACK, "valor fixo (PTAX indisponível)"


def get_usd_to_brl() -> tuple[float, str]:
    """Current dollar rate in reais and where it came from."""
    return _usd_to_brl_of(today_in_brazil().date())


def estimate_cost_usd(usage_by_model: dict) -> float:
    """Cost of every LLM call of one question.

    usage_by_model comes from LangChain's get_usage_metadata_callback:
    {"gemini-2.5-flash": {"input_tokens": 1200, "output_tokens": 300, ...}, ...}
    """
    total = 0.0
    for model, usage in usage_by_model.items():
        name = model.removeprefix("models/")
        input_price, output_price = PRICES_USD_PER_1M_TOKENS.get(
            name, PRICES_USD_PER_1M_TOKENS.get(LLM_MODEL, (0.0, 0.0))
        )
        total += usage.get("input_tokens", 0) / 1_000_000 * input_price
        total += usage.get("output_tokens", 0) / 1_000_000 * output_price
    return round(total, 8)
