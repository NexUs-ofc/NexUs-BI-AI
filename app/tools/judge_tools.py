"""Validation used by the Judge agent to mitigate hallucinations (plain Python, no LLM: deterministic).

- check_numbers: numbers of the answer that do not appear in the context. It ALWAYS runs (called by the
  code in core/judge.py), because an LLM with structured output may skip optional tools.
- search_context: tool the judge LLM may call to confirm names and facts (region, product, schedule...).

The answer and the context are bound when the tool is built, so the LLM cannot change them.
"""
import re
import unicodedata

from langchain_core.tools import StructuredTool

from app.prompts.tools import (
    ALL_NUMBERS_FOUND,
    NO_NUMBERS,
    NUMBERS_NOT_FOUND,
    SEARCH_CONTEXT_DESCRIPTION,
    TERM_NOT_FOUND,
)

_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")  # 1.250.000 (Brazilian thousands separator)
MAX_LINES = 10


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


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _format(number: float) -> str:
    return str(int(number)) if number.is_integer() else str(number)


def check_numbers(answer: str, context: str) -> str:
    """List the relevant numbers of the answer that are not in the context."""
    context_numbers = extract_numbers(context)
    relevant = sorted(n for n in extract_numbers(answer) if _is_relevant(n))
    if not relevant:
        return NO_NUMBERS
    missing = [n for n in relevant if n not in context_numbers and -n not in context_numbers]
    if not missing:
        return ALL_NUMBERS_FOUND
    return NUMBERS_NOT_FOUND.format(numbers=", ".join(_format(n) for n in missing))


def build_judge_tools(context: str) -> list[StructuredTool]:
    def search_context(term: str) -> str:
        wanted = _normalize(term)
        lines = [line for line in re.split(r"\n|(?<=[,{}\[\]])", context) if wanted in _normalize(line)]
        return "\n".join(line.strip() for line in lines[:MAX_LINES]) or TERM_NOT_FOUND.format(term=term)

    return [StructuredTool.from_function(search_context, name="search_context", description=SEARCH_CONTEXT_DESCRIPTION)]
