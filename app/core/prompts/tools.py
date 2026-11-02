"""Tool descriptions. They are read by the LLM to decide when and how to call each tool."""

SEARCH_REPORTS_BY_PERIOD_DESCRIPTION = """Busca os relatórios consolidados mensais de um período específico.
Use SEMPRE que o usuário citar um mês, um ano ou um intervalo de datas.
- Para um único mês, informe só start_month e start_year.
- Para um intervalo, informe também end_month e end_year (inclusivos).
- Converta datas relativas usando a data de hoje informada no seu prompt.
Exemplos (supondo hoje = 15/07/2026):
- "maio de 2026" -> start_month=5, start_year=2026
- "mês passado" -> start_month=6, start_year=2026
- "primeiro trimestre de 2026" -> start_month=1, start_year=2026, end_month=3, end_year=2026
- "este ano" -> start_month=1, start_year=2026, end_month=7, end_year=2026
- "comparar abril com maio" -> start_month=4, start_year=2026, end_month=5, end_year=2026"""

GET_LATEST_REPORTS_DESCRIPTION = """Busca os relatórios consolidados mais recentes.
Use quando o usuário perguntar sobre os indicadores ou a empresa SEM citar mês, ano ou período.
O parâmetro limit define quantos meses trazer: use 1 para "os indicadores atuais" ou "o último mês" e 2 a 3
apenas para comparar meses ou ver tendência (cada mês a mais deixa a resposta mais lenta).
Exemplos: "quais os principais KPIs?" -> limit=1; "como evoluiu o desperdício?" -> limit=3"""

NO_REPORTS_FOUND = "Nenhum relatório encontrado para {scope}."
INVALID_PERIOD = "Período inválido: {reason}"

# --- FAQ retriever (FAQ agent)
SEARCH_FAQ_DESCRIPTION = """Busca no FAQ oficial da empresa (base vetorial) os itens mais parecidos com a consulta.
Use para QUALQUER fato da empresa ou do sistema: o que o NexUs BI faz, horários, suporte, frequência dos
relatórios, origem dos dados, regras. Não use para saudações nem para conceitos gerais de BI.
Se a pergunta tiver várias partes sobre a empresa, chame uma vez para cada parte.
Exemplos: "qual o horário do suporte?" -> query="horário do suporte";
"de onde vêm os dados e quando atualizam?" -> query="origem dos dados" e query="frequência de atualização dos relatórios"."""

NO_FAQ = "(A busca no FAQ não encontrou itens para esta consulta.)"

# --- Conferência de números (orchestrator + tools/judge_tools.py)
ALL_NUMBERS_FOUND = "Todos os números relevantes da resposta aparecem no contexto."
NUMBERS_NOT_FOUND = "Números da resposta que NÃO aparecem no contexto: {numbers}"
NO_NUMBERS = "A resposta não tem números relevantes para conferir."
