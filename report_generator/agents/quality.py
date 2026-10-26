"""Checagem automática: todo número da narrativa precisa existir nos dados ou nas saídas das tools.

Não bloqueia a geração (o relatório nasce como rascunho); o resultado vai para `qualidade` no JSON e
aparece na revisão antes de publicar.
"""
import json
import re

_NUMBER = re.compile(r"(?<![\w/])-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|(?<![\w/])-?\d+(?:,\d+)?")


def _parse_br(token: str) -> float:
    return float(token.replace(".", "").replace(",", "."))


def _collect(value, out: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.add(round(abs(float(value)), 2))
    elif isinstance(value, dict):
        for v in value.values():
            _collect(v, out)
    elif isinstance(value, list):
        for v in value:
            _collect(v, out)


def known_numbers(*sources) -> set[float]:
    """Números de dicts/listas e de textos JSON (saídas das tools)."""
    out: set[float] = set()
    for source in sources:
        if isinstance(source, str):
            try:
                _collect(json.loads(source), out)
            except ValueError:
                continue
        else:
            _collect(source, out)
    return out


def unsupported_numbers(narrativa: dict, known: set[float]) -> list[str]:
    text = json.dumps(narrativa, ensure_ascii=False)
    missing = []
    for token in _NUMBER.findall(text):
        value = abs(_parse_br(token))
        if value <= 31 and float(value).is_integer():  # dias, meses, posições de ranking, contagens pequenas
            continue
        if 2000 <= value <= 2100:  # anos
            continue
        tolerance = 0.051 if "," in token else 0.5  # inteiro no texto pode ser um decimal arredondado
        if not any(abs(value - k) <= tolerance for k in known):
            missing.append(token)
    return sorted(set(missing))
