"""Conferência dos números da resposta contra os dados consultados (Python puro, sem LLM: determinística).

Substitui o juiz por LLM: em vez de uma ou duas chamadas extras ao Gemini com todo o contexto, o código
lista os números relevantes da resposta que não aparecem no que as tools devolveram. Aceita:
- o mesmo número escrito de outro jeito (1.250.000 | 1250000 | 4,2 | 4.2);
- arredondamento do dado para 0, 1 ou 2 casas (14,07 no relatório -> 14,1 na resposta);
- soma ou diferença de dois números do contexto (o prompt manda mostrar a conta: 15,0 - 14,1 = 0,9).
"""
import re

from langsmith import traceable

from app.core.prompts.tools import ALL_NUMBERS_FOUND, NO_NUMBERS, NUMBERS_NOT_FOUND

_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")  # 1.250.000 (Brazilian thousands separator)
_MAX_CONTEXT_NUMBERS = 5000  # above this the sum/difference check is skipped (cost grows with the context)


def _to_float(raw: str) -> float | None:
    """Read numbers written as 1.250.000 | 1.250.000,50 | 4,2 | 4.2 | 1250000."""
    if "," in raw:  # comma is the decimal separator; dots are thousands
        raw = raw.replace(".", "").replace(",", ".")
    elif _THOUSANDS.fullmatch(raw):
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def extract_numbers(text: str) -> set[float]:
    numbers = {_to_float(raw) for raw in _NUMBER.findall(text)}
    return {n for n in numbers if n is not None}


def _is_relevant(number: float) -> bool:
    """Ignore days/months/small counts (<= 31) and years, which appear everywhere."""
    return not (number <= 31 or (number.is_integer() and 1900 <= number <= 2100))


def _format(number: float) -> str:
    return str(int(number)) if number.is_integer() else str(number)


def _known(number: float, rounded: set[float], context: list[float]) -> bool:
    if round(number, 2) in rounded:
        return True
    if len(context) > _MAX_CONTEXT_NUMBERS:
        return False
    for a in context:  # number = a + b  or  number = |a - b|
        if round(number - a, 2) in rounded or round(a - number, 2) in rounded or round(a + number, 2) in rounded:
            return True
    return False


def missing_numbers(answer: str, context: str) -> list[float]:
    """Relevant numbers of the answer that are not in the context (nor a rounding/sum/difference of them)."""
    context_numbers = sorted(extract_numbers(context))
    rounded: set[float] = set()
    for n in context_numbers:
        for digits in (0, 1, 2):
            rounded.add(round(n, digits))
            rounded.add(-round(n, digits))
    relevant = sorted(n for n in extract_numbers(answer) if _is_relevant(n))
    return [n for n in relevant if not _known(n, rounded, context_numbers)]


@traceable(name="check_numbers")
def check_numbers(answer: str, context: str) -> str:
    """Readable version of missing_numbers (debug steps and metrics)."""
    if not any(_is_relevant(n) for n in extract_numbers(answer)):
        return NO_NUMBERS
    missing = missing_numbers(answer, context)
    if not missing:
        return ALL_NUMBERS_FOUND
    return NUMBERS_NOT_FOUND.format(numbers=format_numbers(missing))


def format_numbers(numbers: list[float]) -> str:
    return ", ".join(_format(n) for n in numbers)
