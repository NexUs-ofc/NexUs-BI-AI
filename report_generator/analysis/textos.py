"""Texto para o leitor: os códigos internos dos indicadores (D1, D2...) não aparecem no relatório.

Os agentes trabalham com os códigos (são as chaves das tools), mas o usuário final não sabe o que "D1" é.
`sem_codigos` troca o código pelo nome do indicador depois que o texto é gerado, como rede de segurança além
da instrução nos prompts.
"""
import re

from report_generator.kpis import KPIS

_PARENTESES = re.compile(r"\s*\(\s*D[1-9](?:\s*(?:,|e|\+|/)\s*D[1-9])*\s*\)")
_CODIGO = re.compile(r"\bD([1-9])\b")
_ROTULO_INICIAL = re.compile(r"^\s*D[1-9]\s*[:\-–·]\s*")


def _nome(match: re.Match) -> str:
    return KPIS[f"D{match.group(1)}"].nome.lower()


def sem_codigos(texto: str) -> str:
    """"A taxa de desperdício (D1) subiu; D2 caiu" -> "A taxa de desperdício subiu; descarte por esquecimento caiu"."""
    if not texto:
        return texto
    texto = _ROTULO_INICIAL.sub("", texto)
    texto = _PARENTESES.sub("", texto)
    return _CODIGO.sub(_nome, texto).strip()


def narrativa_sem_codigos(narrativa: dict) -> dict:
    """Aplica `sem_codigos` aos textos da narrativa (os campos `kpi`/`kpis` ficam: são chaves internas)."""
    n = dict(narrativa)
    n["resumo_executivo"] = sem_codigos(n.get("resumo_executivo", ""))
    n["analise_por_kpi"] = [{**a, "texto": sem_codigos(a["texto"])} for a in n.get("analise_por_kpi", [])]
    n["insights"] = [{**i, "titulo": sem_codigos(i["titulo"]), "texto": sem_codigos(i["texto"])}
                     for i in n.get("insights", [])]
    n["recomendacoes"] = [sem_codigos(r) for r in n.get("recomendacoes", [])]
    n["limitacoes"] = [sem_codigos(x) for x in n.get("limitacoes", [])]
    return n
