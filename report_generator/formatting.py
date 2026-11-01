"""Formatação de números no padrão brasileiro (usada nos textos e no template)."""


def br(value, decimals: int = 1) -> str:
    if value is None:
        return "—"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value, decimals: int = 1) -> str:
    return "—" if value is None else f"{br(value, decimals)}%"


def pp(value, decimals: int = 1) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{br(value, decimals)} p.p."


def integer(value) -> str:
    return br(value, 0)
