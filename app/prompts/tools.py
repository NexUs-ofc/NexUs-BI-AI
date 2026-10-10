"""Tool descriptions. They are read by the LLM to decide when and how to call each tool."""

SEARCH_REPORTS_BY_PERIOD_DESCRIPTION = """Busca os relatórios consolidados mensais de um período específico.
Use SEMPRE que o usuário citar um mês, um ano ou um intervalo de datas (ex.: "maio de 2026",
"primeiro trimestre de 2026", "de janeiro a março", "mês passado", "este ano").
- Para um único mês, informe só start_month e start_year.
- Para um intervalo, informe também end_month e end_year (inclusivos).
- Converta datas relativas ("mês passado", "último trimestre") usando a data de hoje informada no seu prompt."""

GET_LATEST_REPORTS_DESCRIPTION = """Busca os relatórios consolidados mais recentes.
Use quando o usuário pedir informações sobre a base, os indicadores ou a empresa SEM citar mês, ano ou período.
O parâmetro limit define quantos relatórios trazer (padrão 3; use mais apenas se precisar comparar mais meses)."""

NO_REPORTS_FOUND = "Nenhum relatório encontrado para {scope}."
INVALID_PERIOD = "Período inválido: {reason}"
