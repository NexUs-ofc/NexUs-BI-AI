"""Input and output guardrails (fixed rules, no LLM).

- Input: blocks prompt injection, illegal content and PII typed by the user.
- Output: masks PII (CPF, CNPJ, e-mail, phone, card) before showing it to the user.
"""
import re

from app.schemas.agents import GuardrailResult

INJECTION_PATTERNS = [
    r"ignore (as|todas as)? ?(instru[cç][oõ]es|regras)",
    r"esque[cç]a (as|suas)? ?(instru[cç][oõ]es|regras)",
    r"ignore (all|previous|the above) instructions",
    r"(mostre|revele|me d[eê]|qual [eé]) (o |seu |sua )?(system prompt|prompt do sistema|senha|token|chave de api|api key)",
    r"senha de admin",
    r"voc[eê] agora [eé] ",
    r"modo (dan|desenvolvedor|developer)",
    r"jailbreak",
]

ILLEGAL_PATTERNS = [
    r"lavar dinheiro|lavagem de dinheiro",
    r"sonega[rç]",
    r"fraud(ar|e)",
    r"hackear|invadir (sistema|conta|banco)",
    r"falsificar",
    r"suborn",
]

# (pattern, label shown to the user). CNPJ comes before CPF/card so it is not masked halfway.
PII_PATTERNS = [
    (r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", "CNPJ"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "CPF"),
    (r"\b(?:\d[ -]?){13,16}\b", "CARTAO"),
    (r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "EMAIL"),
    (r"\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b", "TELEFONE"),
]

MAX_INPUT_LENGTH = 2000


def _matches(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def mask_pii(text: str) -> str:
    for pattern, label in PII_PATTERNS:
        text = re.sub(pattern, f"[{label} REMOVIDO]", text, flags=re.IGNORECASE)
    return text


def input_guardrail(text: str) -> GuardrailResult:
    clean = text.strip()
    if not clean:
        return GuardrailResult(allowed=False, reason="Mensagem vazia.")
    if len(clean) > MAX_INPUT_LENGTH:
        return GuardrailResult(allowed=False, reason=f"Mensagem muito longa (limite de {MAX_INPUT_LENGTH} caracteres).")
    if _matches(INJECTION_PATTERNS, clean):
        return GuardrailResult(allowed=False, reason="Não posso atender a esse pedido: ele tenta alterar minhas regras ou acessar dados restritos.")
    if _matches(ILLEGAL_PATTERNS, clean):
        return GuardrailResult(allowed=False, reason="Não posso ajudar com atividades ilegais.")
    # PII typed by the user never reaches the LLM
    return GuardrailResult(allowed=True, text=mask_pii(clean))


def output_guardrail(text: str) -> GuardrailResult:
    return GuardrailResult(allowed=True, text=mask_pii(text))
