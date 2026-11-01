"""Tools de cálculo: aritmética feita por código, não pelo modelo (o LLM erra conta com confiança)."""
import numpy as np
from langchain_core.tools import StructuredTool

from report_generator.kpis import KPIS, kpi_status
from report_generator.tools.common import to_json


def variacao(atual: float, anterior: float) -> str:
    """Compara dois valores: diferença absoluta (em pontos percentuais quando os dois são %) e variação
    relativa em %. Ex.: atual=12.5, anterior=15.0 -> diferenca=-2.5 (p.p.), variacao_relativa_pct=-16.7."""
    diff = round(atual - anterior, 2)
    rel = round(100 * (atual - anterior) / anterior, 1) if anterior else None
    sentido = "estável" if abs(diff) < 0.05 else ("alta" if diff > 0 else "queda")
    return to_json({"atual": atual, "anterior": anterior, "diferenca": diff, "variacao_relativa_pct": rel,
                    "sentido": sentido})


def comparar_com_meta(codigo: str, valor: float) -> str:
    """Status de um KPI contra a meta (D1, D3, D4, D6, D8) e a distância até ela, em pontos percentuais."""
    kpi = KPIS.get(codigo.upper())
    if not kpi or kpi.meta is None:
        return to_json({"erro": f"{codigo} não tem meta. KPIs com meta: D1, D3, D4, D6, D8."})
    return to_json({"codigo": kpi.codigo, "valor": valor, "meta": kpi.meta, "regra": kpi.regra,
                    "status": kpi_status(kpi.codigo, valor), "distancia_da_meta_pp": round(valor - kpi.meta, 2)})


def tendencia(valores: list[float]) -> str:
    """Tendência de uma série mensal em ordem cronológica (do mais antigo para o mais recente): inclinação
    por mês (regressão linear), direção, média, mínimo, máximo e meses seguidos no mesmo sentido.
    Use com a saída de historico_kpi somada ao valor do mês atual."""
    serie = np.array([v for v in valores if v is not None], dtype=float)
    if serie.size < 2:
        return to_json({"erro": "São necessários ao menos 2 valores."})
    slope = float(np.polyfit(np.arange(serie.size), serie, 1)[0])
    steps = np.sign(np.diff(serie))
    streak = 1
    for s in steps[::-1][1:]:
        if s != steps[-1] or s == 0:
            break
        streak += 1
    direcao = "estável" if abs(slope) < 0.1 else ("alta" if slope > 0 else "queda")
    return to_json({"meses": int(serie.size), "inclinacao_por_mes": round(slope, 2), "direcao": direcao,
                    "media": round(float(serie.mean()), 2), "minimo": float(serie.min()),
                    "maximo": float(serie.max()), "meses_seguidos_no_mesmo_sentido": streak if steps[-1] else 0})


def participacao(parte: float, total: float) -> str:
    """Quanto `parte` representa de `total`, em %."""
    if not total:
        return to_json({"erro": "total igual a zero."})
    return to_json({"parte": parte, "total": total, "participacao_pct": round(100 * parte / total, 1)})


def build_calc_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(f) for f in (variacao, comparar_com_meta, tendencia, participacao)]
