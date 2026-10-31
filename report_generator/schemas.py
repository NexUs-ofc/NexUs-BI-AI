"""Contrato do JSON do relatório mensal (o que vai para o MongoDB, para o PDF e para o chatbot).

Dois blocos com papéis diferentes:
- dados: números calculados por código (determinísticos): pela camada Gold do Databricks ou, em
  desenvolvimento, pela análise do mock. É o que o mês seguinte lê como histórico.
  Campos que a fonte não fornece ficam null (ex.: quartis de vida útil e alimentos abaixo do mínimo na Gold).
- narrativa: textos escritos pelos agentes a partir de `dados`. Nunca é usada como fonte de número.
"""
from datetime import datetime

from pydantic import BaseModel, Field

SCHEMA_VERSION = 2


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
    itens: int | None
    media: float | None
    mediana: float | None = None
    p25: float | None = None
    p75: float | None = None
    minimo: float | None = None
    maximo: float | None = None
    outliers: int | None = None
    mediana_mes_anterior: float | None = None


class LinhaUF(BaseModel):
    uf: str
    households: int | None = None
    suprimido: bool = False  # True = amostra abaixo do mínimo de privacidade; números omitidos
    itens_com_validade: int | None = None
    vencidos: int | None = None
    a_vencer_30d: int | None = None
    d3_pct_vencidos: float | None = None
    d5_pontuacao: int | None = Field(None, description="Unidades vencidas ou vencendo em até 30 dias")
    d5_pct_em_risco: float | None = Field(None, description="D5: % das unidades em risco (define o ranking)")
    d5_rank: int | None = None


class LinhaCategoria(BaseModel):
    categoria: str
    itens_com_validade: int | None = None
    households_com_categoria: int | None = None
    d4_pct_a_vencer_7d: float | None = None
    expirados_no_mes: int | None = Field(None, description="Itens/unidades descartados por vencimento no período")
    d9_indice_desperdicio: float | None = None
    d7_mediana_dias: float | None = None
    d5_pontuacao: int | None = None
    pct_do_desperdicio: float | None = Field(None, description="% do total descartado que é desta categoria")


class AlimentoAbaixoMinimo(BaseModel):
    alimento: str
    categoria: str
    households: int


class Base(BaseModel):
    households: int | None
    itens_na_despensa: int | None = Field(description="Itens (mock) ou unidades (Gold) na despensa")
    eventos_no_mes: int | None = Field(description="Eventos (mock) ou operações de saída (Gold) no mês")
    data_referencia: str


class ResumoMes(BaseModel):
    """Números do topo do relatório (KPIs de EVENTO: dependem só do mês, nunca da foto da despensa)."""
    unidades_saidas: int | None = Field(None, description="Unidades que saíram da despensa (consumo + descarte)")
    unidades_descartadas: int | None = None
    casas_com_movimento: int | None = Field(None, description="Households com ao menos 1 consumo ou descarte")
    avaliados: int = Field(0, description="KPIs com meta e valor no mês")
    fora_da_meta: int = Field(0, description="Desses, quantos ficaram fora da meta")


class PontoMensal(BaseModel):
    ano_mes: str  # AAAA-MM
    d1: float | None = None
    d2: float | None = None
    completo: bool = True  # False = mês ainda em andamento


class DesperdicioCategoria(BaseModel):
    """Evento do mês por categoria. D9 = unidades descartadas ÷ casas que movimentaram a categoria no mês."""
    categoria: str
    unidades_descartadas: int
    unidades_saidas: int
    casas: int = Field(description="Households que consumiram ou descartaram a categoria no mês")
    d1_pct: float | None = None
    d9_indice: float | None = None
    pct_do_desperdicio: float | None = Field(None, description="% do total descartado que é desta categoria")


class DesperdicioRegiao(BaseModel):
    regiao: str
    unidades_descartadas: int
    unidades_saidas: int
    d1_pct: float | None = None
    d2_pct: float | None = None


class MomentoDescarte(BaseModel):
    momento: str  # rótulo legível (ex.: "Antes de vencer")
    unidades: int
    pct: float | None = None


class Dados(BaseModel):
    base: Base
    kpis: dict[str, KpiValor]
    vida_util: VidaUtil
    por_uf: list[LinhaUF]
    por_categoria: list[LinhaCategoria]
    top_abaixo_minimo: list[AlimentoAbaixoMinimo]
    # --- v2: KPIs de evento por mês + disponibilidade da despensa (todos opcionais: relatórios antigos valem)
    tem_despensa: bool = Field(True, description="False = o mês não tem foto da despensa; indicadores de estado omitidos")
    parcial: bool = Field(False, description="True = mês ainda em andamento")
    data_foto_despensa: str | None = None
    resumo: ResumoMes | None = None
    evolucao: list[PontoMensal] = Field(default_factory=list)
    desperdicio_categoria: list[DesperdicioCategoria] = Field(default_factory=list)
    desperdicio_regiao: list[DesperdicioRegiao] = Field(default_factory=list)
    momento_descarte: list[MomentoDescarte] = Field(default_factory=list)


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


# ---------------------------------------------------------------- ações do app (regras em código)
class AcaoApp(BaseModel):
    """Recomendação concreta para o app, ligada a um número do mês. Gerada por regras (analysis/acoes.py),
    nunca pelo LLM, então o número citado sempre bate com `dados`."""
    id: str  # alerta_pos_vencimento | lembrete_perecivel | cadastro_validade | ...
    titulo: str
    texto: str
    evidencia: str  # o número que motivou a ação
    prioridade: int = 2  # 1 = alta


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
    acoes_app: list[AcaoApp] = Field(default_factory=list)
    parcial: bool = False  # True = mês em andamento (relatório diário); vira False quando o mês fecha
    qualidade: dict = Field(default_factory=dict)  # checagens automáticas (ex.: números fora dos dados)
    pdf: Arquivo | None = None
