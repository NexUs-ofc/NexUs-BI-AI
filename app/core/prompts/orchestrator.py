"""Fixed messages and the revision instruction used by the Orchestrator.

The Orchestrator itself is plain Python (no LLM). Its only "prompt" is JUDGE_REVISION: when the judge
rejects an answer, the specialist runs again with this text instead of the original question.
JUDGE_REVISION uses str.format, so its variables are filled before reaching the LLM.
"""

OUT_OF_SCOPE_ANSWER = (
    "Esse assunto está fora do meu escopo. Posso ajudar com dúvidas gerais sobre o NexUs BI, "
    "análises descritivas dos relatórios da empresa e percepções/insights sobre esses dados."
)

REJECTED_ANSWER = (
    "Não consegui gerar uma resposta confiável para essa pergunta com os dados disponíveis. "
    "Pode reformular ou detalhar um pouco mais (por exemplo, citando o mês ou o período)?"
)

LIMIT_REACHED_ANSWER = (
    "Essa pergunta exigiu mais consultas do que o permitido para uma única mensagem. "
    "Pode dividir em perguntas menores ou indicar um período mais curto?"
)

JUDGE_REVISION = """{question}

[REVISÃO INTERNA - não mencione esta revisão ao usuário]
Sua resposta anterior foi reprovada pelo controle de qualidade.
Resposta anterior:
{previous_answer}

Problema apontado: {reason}

Escreva uma nova resposta completa para a pergunta acima corrigindo o problema.
Consulte as tools de novo se precisar de dados. Mantenha o que estava correto.

Exemplo: se o problema apontado for "faltou responder qual região vendeu mais", repita a parte correta
da resposta anterior e acrescente a região, com o número e o mês do relatório."""
