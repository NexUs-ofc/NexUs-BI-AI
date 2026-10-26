"""Tools de análise descritiva manual: expõem aos agentes o bloco `dados` já calculado do mês.

Os agentes NÃO recalculam nada: só consultam o que a análise (analysis/descriptive.py) produziu.
"""
from langchain_core.tools import StructuredTool

from report_generator.kpis import KPIS
from report_generator.schemas import Dados
from report_generator.tools.common import to_json

CATEGORY_SORT_FIELDS = {"d9_indice_desperdicio", "d4_pct_a_vencer_7d", "d5_pontuacao", "expirados_no_mes",
                        "households_com_categoria", "d7_mediana_dias"}


def build_analysis_tools(dados: Dados) -> list[StructuredTool]:
    def consultar_kpis() -> str:
        """KPIs do mês em forma de card (D1, D3, D4, D6, D8): valor, meta, status (calculado por código),
        numerador, denominador, valor do mês anterior e variação em pontos percentuais. Também traz as
        fórmulas e o tamanho da base (households, itens, eventos). Chame esta tool primeiro."""
        return to_json({
            "base": dados.base.model_dump(),
            "kpis": {k: v.model_dump() for k, v in dados.kpis.items()},
            "formulas": {k: d.formula for k, d in KPIS.items()},
        })

    def consultar_vida_util() -> str:
        """D7 - vida útil no cadastro (expiry_date - created_at, em dias): média, mediana, quartis, mínimo,
        máximo, nº de outliers e a mediana do mês anterior. A mediana por categoria está em
        consultar_por_categoria."""
        return to_json(dados.vida_util.model_dump())

    def consultar_por_uf() -> str:
        """Resultados por UF: households, % de vencidos (D3) e ranking de vencimento (D5: DENSE_RANK de
        vencidos + a vencer em 30 dias, 1 = mais crítico). UFs com `suprimido=true` têm poucos households
        e os números foram omitidos por privacidade: nunca estime valores para elas."""
        return to_json([r.model_dump() for r in dados.por_uf])

    def consultar_por_categoria(ordenar_por: str = "d9_indice_desperdicio", limite: int = 17) -> str:
        """Resultados por categoria de alimento: % a vencer em 7 dias (D4), índice de desperdício (D9 =
        expirados no mês / households com a categoria), mediana de vida útil (D7) e pontuação de
        vencimento (D5). ordenar_por: d9_indice_desperdicio (padrão), d4_pct_a_vencer_7d, d5_pontuacao,
        expirados_no_mes, households_com_categoria ou d7_mediana_dias. limite: quantas categorias trazer."""
        field = ordenar_por if ordenar_por in CATEGORY_SORT_FIELDS else "d9_indice_desperdicio"
        rows = sorted(dados.por_categoria, key=lambda r: -(getattr(r, field) or 0))
        return to_json([r.model_dump() for r in rows[: max(1, int(limite))]])

    def consultar_abaixo_minimo() -> str:
        """D6 - top alimentos com mais households abaixo da quantidade mínima configurada."""
        return to_json([r.model_dump() for r in dados.top_abaixo_minimo])

    return [StructuredTool.from_function(f) for f in (
        consultar_kpis, consultar_vida_util, consultar_por_uf, consultar_por_categoria, consultar_abaixo_minimo)]
