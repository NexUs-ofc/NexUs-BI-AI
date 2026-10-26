"""Tools de leitura dos JSONs dos relatórios anteriores no MongoDB (histórico).

Leem só o bloco `dados` (números). A narrativa dos meses passados não é usada como fonte.
"""
from langchain_core.tools import StructuredTool

from report_generator.config import HISTORY_MONTHS
from report_generator.kpis import CARD_KPIS
from report_generator.storage.mongo import find_previous_dados
from report_generator.tools.common import to_json


def _kpi_value(dados: dict, codigo: str) -> float | None:
    if codigo == "D7":
        return (dados.get("vida_util") or {}).get("mediana")
    return ((dados.get("kpis") or {}).get(codigo) or {}).get("valor")


def build_history_tools(ano: int, mes: int, previous: list[dict] | None = None) -> list[StructuredTool]:
    """`previous` permite injetar o histórico já lido (evita ir ao Mongo de novo e facilita testes)."""
    history = previous if previous is not None else find_previous_dados(ano, mes, HISTORY_MONTHS)

    def historico_kpi(codigo: str, meses: int = HISTORY_MONTHS) -> str:
        """Série histórica de um KPI nos meses ANTERIORES ao relatório atual, em ordem cronológica (do mais
        antigo para o mais recente). codigo: D1, D3, D4, D6, D8 ou D7 (mediana de vida útil).
        Para a tendência, junte o valor do mês atual no fim e chame a tool tendencia."""
        codigo = codigo.upper()
        if codigo not in [*CARD_KPIS, "D7"]:
            return to_json({"erro": f"KPI {codigo} sem série histórica. Use: {', '.join(CARD_KPIS)} ou D7."})
        rows = [{"mes": f"{h['mes']:02d}/{h['ano']}", "valor": _kpi_value(h["dados"], codigo)}
                for h in history[: max(1, int(meses))]]
        if not rows:
            return to_json({"aviso": "Não há relatórios anteriores na base. Não fale em tendência."})
        return to_json({"codigo": codigo, "serie": rows[::-1]})

    def relatorio_anterior(meses_atras: int = 1) -> str:
        """Bloco `dados` completo de um relatório anterior (1 = mês passado, 2 = dois meses atrás...).
        Use para comparar UFs e categorias com meses passados."""
        idx = max(1, int(meses_atras)) - 1
        if idx >= len(history):
            return to_json({"aviso": f"Não há relatório de {meses_atras} mês(es) atrás na base."})
        h = history[idx]
        return to_json({"mes": f"{h['mes']:02d}/{h['ano']}", "dados": h["dados"]})

    return [StructuredTool.from_function(f) for f in (historico_kpi, relatorio_anterior)]
