"""Contract of GET /metrics/report."""
from pydantic import BaseModel, Field


class LatencyStats(BaseModel):
    avg_ms: float
    p95_ms: float


class ToolStats(BaseModel):
    calls: int
    error_rate: float
    avg_ms: float
    p95_ms: float


class Scenario(BaseModel):
    weekly_users: int
    weekly_questions: int
    weekly_cost_brl: float
    monthly_cost_brl: float
    weekly_savings_brl: float
    roi: float | None = Field(description="(economia - custo) / custo; 2.0 = a economia é 3x o custo")


class MetricsReport(BaseModel):
    period_days: int
    questions: int
    resolved: int
    resolution_rate: float
    error_rate: float = Field(description="Perguntas que terminaram em erro (exceção) / total")
    judge_rejection_rate: float = Field(description="Perguntas reprovadas pelo juiz até o fim / total")
    blocked_rate: float = Field(description="Perguntas bloqueadas pelo guardrail / total")
    latency_total: LatencyStats
    latency_by_node: dict[str, LatencyStats] = Field(description="Latência de cada nó do grafo (interagentes)")
    tools: dict[str, ToolStats] = Field(description="Chamadas, erros e latência de cada tool (coleção tool_metrics_bi)")
    input_tokens: int
    output_tokens: int
    total_cost_brl: float
    avg_cost_per_question_brl: float
    cost_per_resolution_brl: float | None
    savings_brl: float
    roi: float | None
    scenarios: list[Scenario]
    assumptions: dict[str, float]
    usd_to_brl_source: str = Field(description="De onde veio a cotação do dólar (PTAX do Banco Central ou valor fixo)")
