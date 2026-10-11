"""Input and output guardrails (fixed rules, no LLM).

- Input: blocks prompt injection, questions about the system internals, illegal content
  and masks PII typed by the user.
- Output: masks PII (CPF, CNPJ, e-mail, phone, card) before showing it to the user.

The patterns are written without accents and in lowercase because the text is normalized
(see _normalize) before matching: "Instruções", "instrucoes" and "INSTRUÇÕES" all match.
"""
import re
import unicodedata

from app.schemas.agents import GuardrailResult

# Attempts to change the assistant's rules or role
INJECTION_PATTERNS = [
    r"\b(ignore|ignora|ignorar|esqueca|esquece|desconsidere|desconsidera)\b.{0,40}\b(instrucoes|regras|orientacoes|prompt)",
    r"\b(ignore|forget|disregard)\b.{0,40}\b(instructions|rules|prompt)",
    r"\b(voce agora e|a partir de agora voce|finja (que e|ser)|you are now|act as)\b",
    r"\bmodo (dan|desenvolvedor|developer|deus|admin)\b",
    r"\bjailbreak\b",
]

# Questions about how the system is built (code, architecture, prompts, credentials)
INTERNALS_PATTERNS = [
    r"\b(back ?-?end|front ?-?end|codigo ?-?fonte|source code|repositorio|github)\b",
    r"\b(system prompt|prompt do sistema|seus? prompts?|suas (instrucoes|regras internas))\b",
    r"\b(variaveis de ambiente|string de conexao|connection string|credenciais?|api ?-?key|chave (de|da) api|token)\b",
    r"\.env\b",
    r"\bsenha (do|de|da) (admin|administrador|banco|sistema|servidor)\b",
    r"\b(arquitetura|estrutura|stack|tecnologias?|infraestrutura|configuracao|implementacao)\b.{0,30}"
    r"\b(sistema|servidor|api|assistente|chatbot|bot|ia|agentes?)\b",
    r"\b(qual|quais|que)\b.{0,20}\b(modelo|llm|banco de dados)\b.{0,25}\b(voce|usa|utiliza|roda)\b",
    r"\bcomo (voce )?(foi|e|esta) (feito|construido|programado|implementado)\b",
    # attempts to make the assistant repeat or reveal its instructions (prompt leak)
    r"\b(repita|repete|reproduza|copie|imprima)\b.{0,60}\b(acima|anterior|anteriores|antes|inicial|instrucoes|prompt)\b",
    r"\b(quais|qual|que|mostre|mostra|liste|diga|revele|conte)\b.{0,30}\b(instrucoes|regras|orientacoes|diretrizes)\b"
    r".{0,30}\b(voce|recebeu|te deram|internas|seguir)\b",
    # the same in English
    r"\b(repeat|print|show|reveal|tell me|what are)\b.{0,40}\b(instructions|rules|prompt|guidelines|text above|previous)\b",
    r"\b(architecture|infrastructure|tech stack|source code)\b",
    r"\bhow (were|are) you (built|made|programmed|implemented)\b",
    r"\bwhat (model|llm|database)\b",
]

# Pieces of the prompts and internal names: if an answer contains one of them, the prompt leaked
LEAK_MARKERS = [
    "voce e o roteador", "voce e o analista", "voce e o recomendador", "voce e o juiz",
    "voce e o assistente do nexus bi", "regras de seguranca", "revisao interna", "regras de desempate",
    "responda apenas com a estrutura pedida", "verificacao automatica dos numeros",
    "search_reports_by_period", "get_latest_reports", "search_faq", "search_context", "check_numbers",
    "routedecision", "create_agent",
]

LEAK_ANSWER = (
    "Não posso compartilhar detalhes internos do sistema. "
    "Posso ajudar com dúvidas sobre o NexUs BI e com análises dos relatórios da empresa."
)

ILLEGAL_PATTERNS = [
    r"lavar dinheiro|lavagem de dinheiro",
    r"\bsonega",
    r"\bfraud(ar|e)",
    r"\bhackear|\binvadir (o |um |uma )?(sistema|conta|banco)",
    r"\bfalsificar",
    r"\bsuborn",
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


def _normalize(text: str) -> str:
    """Lowercase and remove accents ("Instruções" -> "instrucoes")."""
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return without_accents.lower()


def _matches(patterns: list[str], text: str) -> bool:
    normalized = _normalize(text)
    return any(re.search(p, normalized) for p in patterns)


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
    if _matches(INTERNALS_PATTERNS, clean):
        return GuardrailResult(
            allowed=False,
            reason="Não posso compartilhar detalhes internos do sistema (código, arquitetura, prompts, modelos ou credenciais). "
            "Posso ajudar com dúvidas sobre o NexUs BI e com análises dos relatórios da empresa.",
        )
    if _matches(ILLEGAL_PATTERNS, clean):
        return GuardrailResult(allowed=False, reason="Não posso ajudar com atividades ilegais.")
    # PII typed by the user never reaches the LLM
    return GuardrailResult(allowed=True, text=mask_pii(clean))


def output_guardrail(text: str) -> GuardrailResult:
    """Last line of defense: never let the prompts or internal names reach the user, and mask PII."""
    normalized = _normalize(text)
    if any(marker in normalized for marker in LEAK_MARKERS):
        return GuardrailResult(allowed=False, reason="vazamento de instruções internas", text=LEAK_ANSWER)
    return GuardrailResult(allowed=True, text=mask_pii(text))
