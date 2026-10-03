"""Guardrails de entrada e saída (regras fixas, sem LLM).

- Entrada: bloqueia injeção de prompt, conteúdo ilegal e PII digitada pelo usuário.
- Saída: mascara PII (CPF, CNPJ, e-mail, telefone, cartão) antes de mostrar ao usuário.
"""
import re

from app.schemas.agentes import ResultadoGuardrail

PADROES_INJECAO = [
    r"ignore (as|todas as)? ?(instru[cç][oõ]es|regras)",
    r"esque[cç]a (as|suas)? ?(instru[cç][oõ]es|regras)",
    r"ignore (all|previous|the above) instructions",
    r"(mostre|revele|me d[eê]|qual [eé]) (o |seu |sua )?(system prompt|prompt do sistema|senha|token|chave de api|api key)",
    r"senha de admin",
    r"voc[eê] agora [eé] ",
    r"modo (dan|desenvolvedor|developer)",
    r"jailbreak",
]

PADROES_ILEGAIS = [
    r"lavar dinheiro|lavagem de dinheiro",
    r"sonega[rç]",
    r"fraud(ar|e)",
    r"hackear|invadir (sistema|conta|banco)",
    r"falsificar",
    r"suborn",
]

PADROES_PII = {
    "CPF": r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
    "CNPJ": r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
    "CARTAO": r"\b(?:\d[ -]?){13,16}\b",
    "EMAIL": r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
    "TELEFONE": r"\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b",
}


def _bate(padroes: list[str], texto: str) -> bool:
    return any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes)


def mascarar_pii(texto: str) -> str:
    # CNPJ antes de CPF/cartão para não ser mascarado pela metade
    for nome in ("CNPJ", "CPF", "CARTAO", "EMAIL", "TELEFONE"):
        texto = re.sub(PADROES_PII[nome], f"[{nome} REMOVIDO]", texto, flags=re.IGNORECASE)
    return texto


def guardrail_entrada(texto: str) -> ResultadoGuardrail:
    t = texto.strip()
    if not t:
        return ResultadoGuardrail(permitido=False, motivo="Mensagem vazia.")
    if len(t) > 2000:
        return ResultadoGuardrail(permitido=False, motivo="Mensagem muito longa (limite de 2000 caracteres).")
    if _bate(PADROES_INJECAO, t):
        return ResultadoGuardrail(permitido=False, motivo="Não posso atender a esse pedido: ele tenta alterar minhas regras ou acessar dados restritos.")
    if _bate(PADROES_ILEGAIS, t):
        return ResultadoGuardrail(permitido=False, motivo="Não posso ajudar com atividades ilegais.")
    # PII digitada pelo usuário não segue para a LLM
    return ResultadoGuardrail(permitido=True, texto=mascarar_pii(t))


def guardrail_saida(texto: str) -> ResultadoGuardrail:
    return ResultadoGuardrail(permitido=True, texto=mascarar_pii(texto))
