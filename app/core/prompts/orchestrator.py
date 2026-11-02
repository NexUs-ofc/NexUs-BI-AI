"""Mensagens fixas e a instrução de revisão usadas pelo Orquestrador.

O Orquestrador é Python puro (sem LLM). REVISION entra no lugar da pergunta quando a conferência de números
(tools/judge_tools.py) encontra na resposta um número que não veio das tools; usa str.format.
"""

REJECTED_ANSWER = (
    "Não consegui gerar uma resposta confiável para essa pergunta com os dados disponíveis. "
    "Pode reformular ou detalhar um pouco mais (por exemplo, citando o mês ou o período)?"
)

LIMIT_REACHED_ANSWER = (
    "Essa pergunta exigiu mais consultas do que o permitido para uma única mensagem. "
    "Pode dividir em perguntas menores ou indicar um período mais curto?"
)

REVISION = """{question}

[REVISÃO INTERNA - não mencione esta revisão ao usuário]
Sua resposta anterior citou números que não aparecem nos dados consultados: {numbers}.
Resposta anterior:
{previous_answer}

Escreva de novo a resposta completa usando somente números que vieram das tools (consulte de novo se
precisar). Se fez uma conta, mostre a conta. Mantenha o que estava correto."""
