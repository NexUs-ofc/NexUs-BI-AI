"""Contrato do JSON do relatório mensal (o que vai para o MongoDB, para o PDF e para o chatbot).

Dois blocos com papéis diferentes:
- dados: números calculados por código (determinísticos). É o que o mês seguinte lê como histórico.
- narrativa: textos escritos pelos agentes a partir de `dados`. Nunca é usada como fonte de número.
"""
from datetime import datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


# ---------------------------------------------------------------- dados (código)
class KpiValor(BaseModel):
    codigo: str
    nome: str
    unidade: str
    valor: float | None
    meta: float | None = None
    regra: str | None = None
    status: str
    numerador: float | None = None
    denominador: float | None = None
    mes_anterior: float | None = None
    variacao_pp: float | None = Field(None, description="Diferença em pontos percentuais contra o mês anterior")


class VidaUtil(BaseModel):
    codigo: str = "D7"
    nome: str = "Vida útil no cadastro"
    unidade: str = "dias"
    itens: int
    media: float | None
    mediana: float | None
    p25: float | None
    p75: float | None
    minimo: float | None
    maximo: float | None
    outliers: int
    mediana_mes_anterior: float | None = None


class LinhaUF(BaseModel):
    uf: str
    households: int
    suprimido: bool = False  # True = menos households que o mínimo de privacidade; números omitidos
    itens_com_validade: int | None = None
    vencidos: int | None = None
    a_vencer_30d: int | None = None
    d3_pct_vencidos: float | None = None
    d5_pontuacao: int | None = None
    d5_rank: int | None = None


class LinhaCategoria(BaseModel):
    categoria: str
    itens_com_validade: int
    households_com_categoria: int
    d4_pct_a_vencer_7d: float | None
    expirados_no_mes: int
    d9_indice_desperdicio: float | None
    d7_mediana_dias: float | None
    d5_pontuacao: int


class AlimentoAbaixoMinimo(BaseModel):
    alimento: str
    categoria: str
    households: int


class Base(BaseModel):
    households: int
    itens_na_despensa: int
    eventos_no_mes: int
    data_referencia: str


class Dados(BaseModel):
    base: Base
    kpis: dict[str, KpiValor]
    vida_util: VidaUtil
    por_uf: list[LinhaUF]
    por_categoria: list[LinhaCategoria]
    top_abaixo_minimo: list[AlimentoAbaixoMinimo]


# ---------------------------------------------------------------- narrativa (agentes)
class AnaliseKpi(BaseModel):
    kpi: str = Field(description="Código do KPI, ex.: D1")
    texto: str = Field(description="2 a 4 frases descrevendo o KPI no mês, com os números dos dados")


class Insight(BaseModel):
    tipo: str = Field(description="alerta | tendencia | destaque")
    titulo: str = Field(description="Frase curta, até 10 palavras")
    texto: str = Field(description="2 a 3 frases com a evidência (números e meses)")
    kpis: list[str] = Field(default_factory=list, description="Códigos dos KPIs envolvidos")


class Narrativa(BaseModel):
    resumo_executivo: str = Field(description="1 parágrafo de 4 a 6 frases com o panorama do mês")
    analise_por_kpi: list[AnaliseKpi]
    insights: list[Insight] = Field(description="3 a 5 insights")
    recomendacoes: list[str] = Field(description="3 a 5 recomendações acionáveis, uma frase cada")
    limitacoes: list[str] = Field(default_factory=list, description="Ressalvas sobre os dados")


# ---------------------------------------------------------------- documento
class Arquivo(BaseModel):
    uri: str
    gerado_em: datetime


class Relatorio(BaseModel):
    ano: int
    mes: int
    status: str = "rascunho"  # rascunho | publicado
    versao_schema: int = SCHEMA_VERSION
    fonte_dados: str
    gerado_em: datetime
    gerado_com_ia: bool
    dados: Dados
    narrativa: Narrativa
    qualidade: dict = Field(default_factory=dict)  # checagens automáticas (ex.: números fora dos dados)
    pdf: Arquivo | None = None
