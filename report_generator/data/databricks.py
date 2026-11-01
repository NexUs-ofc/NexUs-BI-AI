"""Leitura da camada Gold do Databricks (workspace.gold.kpi_*), via databricks-sql-connector.

Liga com REPORT_DATA_SOURCE=databricks. As tabelas são atualizadas todo dia às 07:00 pelo Job_NexUs_BI e já
trazem os KPIs oficiais agregados (percentuais 0-100, "unidades" = embalagens, sem peso nem R$). Só as
tabelas kpi_* são lidas: são pequenas, e o warehouse da Free Edition tem cota diária (a API guarda o
resultado em cache; o relatório consulta uma vez por mês).

    kpi_desperdicio_mensal  1 linha por mês: D1, D2 e volumes (série do gráfico mensal)
    kpi_estado_diario       1 linha por dia: foto da despensa (D3, D4, D6, D7, D8); usamos a última do mês
    kpi_uf                  1 linha por UF (foto de hoje): D5 e recortes por UF
    kpi_cards               1 linha por KPI: só a data da foto (data_referencia)

Os recortes que as kpi_* não têm saem das tabelas fato_* com dim_*, já AGREGADOS no warehouse (as consultas
devolvem dezenas de linhas, nunca o fato inteiro):

    regiao_categoria   fato_movimento do mês x dim_alimento x dim_localidade: unidades descartadas e
                       consumidas por categoria e região
    estoque_categoria  última foto do mês em fato_estoque: lotes, D4 e quartis de vida útil por categoria
    estoque_total      a mesma foto: households, quartis e outliers da vida útil
    vida_util_faixas   a mesma foto: histograma da vida útil
    abaixo_minimo      última foto do mês em fato_estoque_minimo: top 10 alimentos abaixo do mínimo

KPIs de EVENTO do mês (só dependem de fato_movimento.ano_mes_evento, existem mesmo sem foto da despensa):

    evento_resumo      unidades que saíram, unidades descartadas, casas com movimento
    evento_categoria   por categoria: descartadas, saídas e casas que a movimentaram (D9 = descartadas ÷ casas)
    evento_regiao      por região: descartadas, saídas e descartes esquecidos (D1 e D2 por região)
    evento_momento     unidades descartadas por momento do descarte (antes de vencer / após vencer / esquecido)

Economia de cota (Free Edition): tudo roda numa única conexão e, se o mês NÃO tem foto da despensa, as
consultas de estado (kpi_uf, estoque_*, abaixo_minimo) nem são enviadas ao warehouse.

.env: DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH (Serverless Starter Warehouse), DATABRICKS_TOKEN,
DATABRICKS_CATALOG=workspace, DATABRICKS_SCHEMA=gold.
"""
import re
from dataclasses import dataclass

import pandas as pd

from report_generator.config import DATABRICKS, GOLD_CACHE_SECONDS

COLUMNS = {
    "kpi_desperdicio_mensal": ["ano_mes", "mes_completo", "operacoes", "unidades_descartadas",
                               "unidades_movimentadas", "d1_pct", "d1_variacao_pp", "d2_esquecidos_pct"],
    "kpi_estado_diario": ["data_referencia", "lotes", "unidades", "d3_vencidos_pct", "d4_vencem_7d_pct",
                          "d8_sem_validade_pct", "d7_vida_util_media", "d6_abaixo_minimo_pct", "ano_mes",
                          "ultimo_dia_do_mes"],
    "kpi_uf": ["uf", "nome_uf", "regiao", "lotes", "unidades", "unidades_em_risco", "pct_em_risco",
               "d3_vencidos_pct", "d4_vencem_7d_pct", "d8_sem_validade_pct", "households_com_minimo",
               "d6_abaixo_minimo_pct", "unidades_movimentadas", "d1_pct"],
    "kpi_cards": ["codigo", "valor", "data_referencia"],
    "regiao_categoria": ["categoria", "regiao", "descartadas", "consumidas"],
    "estoque_categoria": ["categoria", "lotes", "unidades_com_validade", "unidades_7d", "q1", "mediana", "q3",
                          "minimo", "maximo"],
    "estoque_total": ["households", "lotes_com_validade", "q1", "mediana", "q3", "minimo", "maximo", "outliers"],
    "vida_util_faixas": ["faixa", "itens"],
    "abaixo_minimo": ["alimento", "categoria", "households", "faltam"],
    "evento_resumo": ["unidades_saidas", "unidades_descartadas", "casas", "operacoes"],
    "evento_categoria": ["categoria", "unidades_descartadas", "unidades_saidas", "casas"],
    "evento_regiao": ["regiao", "unidades_descartadas", "unidades_saidas", "descartadas_com_validade",
                      "esquecidas"],
    "evento_momento": ["momento", "unidades"],
    "evento_atraso_faixas": ["inicio", "unidades"],
    "evento_atraso_categoria": ["categoria", "q1", "mediana", "q3", "minimo", "maximo", "unidades"],
}
TEXT_COLUMNS = {"ano_mes", "uf", "nome_uf", "regiao", "categoria", "codigo", "data_referencia", "faixa", "alimento",
                "momento"}
# Consultas que só fazem sentido se o mês tem foto da despensa (kpi_estado_diario devolveu linha)
STATE_TABLES = {"kpi_uf", "kpi_cards", "estoque_categoria", "estoque_total", "vida_util_faixas",
                "abaixo_minimo"}
# Faixas do histograma de vida útil (as mesmas do mock em analysis/dashboard.py)
SHELF_LIFE_BUCKETS = [(0, 7, "0-7"), (8, 14, "8-14"), (15, 21, "15-21"), (22, 28, "22-28"), (29, 35, "29-35"),
                      (36, None, "36-mais")]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass
class GoldData:
    ano: int
    mes: int
    mensal: pd.DataFrame  # meses até (ano, mes), em ordem cronológica
    estado: pd.DataFrame  # 0 ou 1 linha: a última foto do mês
    uf: pd.DataFrame
    data_foto: str | None  # dia da foto usada em kpi_uf
    fatos: dict[str, pd.DataFrame]  # recortes agregados das tabelas fato_* (regiao_categoria, estoque_*...)


def ano_mes(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


def _ident(name: str) -> str:
    """Catálogo/schema vindos do .env: só letras, números e _ (evita SQL injection)."""
    if not _IDENTIFIER.match(name or ""):
        raise ValueError(f"Nome inválido no .env do Databricks: {name!r}")
    return f"`{name}`"


def table_name(table: str) -> str:
    return ".".join(_ident(p) for p in (DATABRICKS["catalog"], DATABRICKS["schema"], table))


def build_queries(ano: int, mes: int) -> dict[str, tuple[str, dict]]:
    """SQL (com parâmetros nomeados) de cada tabela. Separado da conexão para dar para testar."""
    am = ano_mes(ano, mes)

    def select(table: str, tail: str = "", params: dict | None = None) -> tuple[str, dict]:
        cols = ", ".join(f"`{c}`" for c in COLUMNS[table])
        return f"SELECT {cols} FROM {table_name(table)}{tail}", params or {}

    return {
        "kpi_desperdicio_mensal": select("kpi_desperdicio_mensal", " WHERE `ano_mes` <= :ano_mes ORDER BY `ano_mes`",
                                         {"ano_mes": am}),
        "kpi_estado_diario": select("kpi_estado_diario", " WHERE `ano_mes` = :ano_mes ORDER BY "
                                    "`ultimo_dia_do_mes` DESC, `data_referencia` DESC LIMIT 1", {"ano_mes": am}),
        "kpi_uf": select("kpi_uf"),
        "kpi_cards": select("kpi_cards", " ORDER BY `data_referencia` DESC LIMIT 1"),
        **{name: (sql, {"ano_mes": am}) for name, sql in _fato_queries().items()},
    }


def _fato_queries() -> dict[str, str]:
    """SQL agregado sobre fato_*/dim_*. A foto da despensa é a última do mês pedido (:ano_mes)."""
    t = {name: table_name(name) for name in ("fato_movimento", "fato_estoque", "fato_estoque_minimo",
                                               "dim_alimento", "dim_localidade")}
    estoque = f"""WITH foto AS (
            SELECT MAX(data_referencia) AS d FROM {t['fato_estoque']} WHERE ano_mes_referencia = :ano_mes),
        base AS (
            SELECT a.categoria, e.sk_perfil, e.quantidade, e.tem_validade, e.vence_7d,
                   CASE WHEN e.tem_validade = 1 THEN e.vida_util_dias END AS v
            FROM {t['fato_estoque']} e JOIN {t['dim_alimento']} a ON a.sk_alimento = e.sk_alimento
            WHERE e.data_referencia = (SELECT d FROM foto))"""
    faixas = " ".join(f"WHEN v >= {lo}" + (f" AND v <= {hi}" if hi is not None else "") + f" THEN '{fid}'"
                      for lo, hi, fid in SHELF_LIFE_BUCKETS)
    evento = f"""FROM {t['fato_movimento']} m"""
    sem_perfil_nulo = "COUNT(DISTINCT CASE WHEN m.sk_perfil <> -1 THEN m.sk_perfil END)"
    return {
        "evento_resumo": f"""
            SELECT SUM(m.unidades) AS unidades_saidas, SUM(m.qtd_descartada) AS unidades_descartadas,
                   {sem_perfil_nulo} AS casas, COUNT(*) AS operacoes
            {evento}
            WHERE m.ano_mes_evento = :ano_mes""",
        "evento_categoria": f"""
            SELECT a.categoria, SUM(m.qtd_descartada) AS unidades_descartadas, SUM(m.unidades) AS unidades_saidas,
                   {sem_perfil_nulo} AS casas
            {evento}
            JOIN {t['dim_alimento']} a ON a.sk_alimento = m.sk_alimento
            WHERE m.ano_mes_evento = :ano_mes
            GROUP BY a.categoria""",
        "evento_regiao": f"""
            SELECT l.regiao, SUM(m.qtd_descartada) AS unidades_descartadas, SUM(m.unidades) AS unidades_saidas,
                   SUM(CASE WHEN m.esquecido IS NOT NULL THEN m.qtd_descartada END) AS descartadas_com_validade,
                   SUM(CASE WHEN m.esquecido = 1 THEN m.qtd_descartada END) AS esquecidas
            {evento}
            JOIN {t['dim_localidade']} l ON l.sk_localidade = m.sk_localidade
            WHERE m.ano_mes_evento = :ano_mes
            GROUP BY l.regiao""",
        "evento_momento": f"""
            SELECT m.momento_descarte AS momento, SUM(m.qtd_descartada) AS unidades
            {evento}
            WHERE m.ano_mes_evento = :ano_mes AND m.expirado = 1
            GROUP BY m.momento_descarte""",
        "evento_atraso_faixas": f"""
            SELECT CAST(FLOOR(m.dias_apos_vencimento / 7) * 7 AS INT) AS inicio, SUM(m.qtd_descartada) AS unidades
            {evento}
            WHERE m.ano_mes_evento = :ano_mes AND m.expirado = 1 AND m.dias_apos_vencimento >= 0
            GROUP BY 1""",
        "evento_atraso_categoria": f"""
            SELECT a.categoria,
                   percentile_approx(m.dias_apos_vencimento, 0.25) AS q1,
                   percentile_approx(m.dias_apos_vencimento, 0.5) AS mediana,
                   percentile_approx(m.dias_apos_vencimento, 0.75) AS q3,
                   MIN(m.dias_apos_vencimento) AS minimo, MAX(m.dias_apos_vencimento) AS maximo,
                   SUM(m.qtd_descartada) AS unidades
            {evento}
            JOIN {t['dim_alimento']} a ON a.sk_alimento = m.sk_alimento
            WHERE m.ano_mes_evento = :ano_mes AND m.expirado = 1 AND m.dias_apos_vencimento >= 0
            GROUP BY a.categoria""",
        "regiao_categoria": f"""
            SELECT a.categoria, l.regiao,
                   SUM(CASE WHEN m.descartado = 1 THEN m.qtd_descartada ELSE 0 END) AS descartadas,
                   SUM(CASE WHEN m.consumido = 1 THEN m.qtd_consumida ELSE 0 END) AS consumidas
            FROM {t['fato_movimento']} m
            JOIN {t['dim_alimento']} a ON a.sk_alimento = m.sk_alimento
            JOIN {t['dim_localidade']} l ON l.sk_localidade = m.sk_localidade
            WHERE m.ano_mes_evento = :ano_mes
            GROUP BY a.categoria, l.regiao""",
        "estoque_categoria": f"""{estoque},
        q AS (
            SELECT categoria, COUNT(*) AS lotes, SUM(quantidade * tem_validade) AS unidades_com_validade,
                   SUM(quantidade * vence_7d) AS unidades_7d, percentile_approx(v, 0.25) AS q1,
                   percentile_approx(v, 0.5) AS mediana, percentile_approx(v, 0.75) AS q3
            FROM base GROUP BY categoria)
        SELECT q.categoria, MAX(q.lotes) AS lotes, MAX(q.unidades_com_validade) AS unidades_com_validade,
               MAX(q.unidades_7d) AS unidades_7d, MAX(q.q1) AS q1, MAX(q.mediana) AS mediana, MAX(q.q3) AS q3,
               MIN(CASE WHEN b.v >= q.q1 - 1.5 * (q.q3 - q.q1) THEN b.v END) AS minimo,
               MAX(CASE WHEN b.v <= q.q3 + 1.5 * (q.q3 - q.q1) THEN b.v END) AS maximo
        FROM q JOIN base b ON b.categoria = q.categoria
        GROUP BY q.categoria""",
        "estoque_total": f"""{estoque},
        q AS (
            SELECT COUNT(DISTINCT sk_perfil) AS households, COUNT(v) AS lotes_com_validade,
                   percentile_approx(v, 0.25) AS q1, percentile_approx(v, 0.5) AS mediana,
                   percentile_approx(v, 0.75) AS q3
            FROM base)
        SELECT MAX(q.households) AS households, MAX(q.lotes_com_validade) AS lotes_com_validade,
               MAX(q.q1) AS q1, MAX(q.mediana) AS mediana, MAX(q.q3) AS q3,
               MIN(CASE WHEN b.v >= q.q1 - 1.5 * (q.q3 - q.q1) THEN b.v END) AS minimo,
               MAX(CASE WHEN b.v <= q.q3 + 1.5 * (q.q3 - q.q1) THEN b.v END) AS maximo,
               COUNT(CASE WHEN b.v < q.q1 - 1.5 * (q.q3 - q.q1) OR b.v > q.q3 + 1.5 * (q.q3 - q.q1)
                          THEN 1 END) AS outliers
        FROM q CROSS JOIN base b""",
        "vida_util_faixas": f"""{estoque}
        SELECT CASE {faixas} END AS faixa, COUNT(*) AS itens
        FROM base WHERE v IS NOT NULL AND v >= 0 GROUP BY 1""",
        "abaixo_minimo": f"""
            WITH foto AS (
                SELECT MAX(data_referencia) AS d FROM {t['fato_estoque_minimo']}
                WHERE date_format(data_referencia, 'yyyy-MM') = :ano_mes)
            SELECT a.alimento, a.categoria, COUNT(DISTINCT m.sk_perfil) AS households,
                   SUM(m.minimo - m.estoque) AS faltam
            FROM {t['fato_estoque_minimo']} m JOIN {t['dim_alimento']} a ON a.sk_alimento = m.sk_alimento
            WHERE m.data_referencia = (SELECT d FROM foto) AND m.abaixo_minimo = 1
            GROUP BY a.alimento, a.categoria
            ORDER BY households DESC, faltam DESC
            LIMIT 10""",
    }


def _connect():
    from databricks import (
        sql,  # import aqui: só é necessário quando a fonte é o Databricks
    )

    names = {"server_hostname": "DATABRICKS_SERVER_HOSTNAME", "http_path": "DATABRICKS_HTTP_PATH",
             "access_token": "DATABRICKS_TOKEN"}
    missing = [env for key, env in names.items() if not DATABRICKS[key]]
    if missing:
        raise RuntimeError("Databricks não configurado no .env: falta " + ", ".join(missing))
    return sql.connect(server_hostname=DATABRICKS["server_hostname"], http_path=DATABRICKS["http_path"],
                       access_token=DATABRICKS["access_token"])


def to_frame(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Confere as colunas e converte DECIMAL (vem como objeto Decimal) em número."""
    missing = [c for c in COLUMNS[table] if c not in df.columns]
    if missing:
        raise ValueError(f"Tabela {table} sem as colunas: {', '.join(missing)}")
    df = df[COLUMNS[table]].copy()
    for col in df.columns:
        if df[col].dtype == object and col not in TEXT_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "data_referencia" in df.columns:
        df["data_referencia"] = pd.to_datetime(df["data_referencia"], errors="coerce").dt.date.astype(str)
    return df


def empty_frame(table: str) -> pd.DataFrame:
    return to_frame(table, pd.DataFrame(columns=COLUMNS[table]))


def load_gold(ano: int, mes: int, connect=_connect) -> GoldData:
    frames = {}
    with connect() as connection, connection.cursor() as cursor:
        for table, (query, params) in build_queries(ano, mes).items():
            if table in STATE_TABLES and frames["kpi_estado_diario"].empty:
                frames[table] = empty_frame(table)  # mês sem foto da despensa: poupa a cota do warehouse
                continue
            cursor.execute(query, params)
            frames[table] = to_frame(table, cursor.fetchall_arrow().to_pandas())
    cards = frames["kpi_cards"]
    return GoldData(ano=ano, mes=mes, mensal=frames["kpi_desperdicio_mensal"], estado=frames["kpi_estado_diario"],
                    uf=frames["kpi_uf"],
                    data_foto=None if cards.empty else cards["data_referencia"].iloc[0],
                    fatos={name: frames[name] for name in _fato_queries()})


# ---------------------------------------------------------------- cache (cota do warehouse)
_cache: dict[tuple[int, int], tuple[float, GoldData]] = {}


def load_gold_cached(ano: int, mes: int, ttl: int | None = None, connect=_connect) -> GoldData:
    """`load_gold` com cache em memória por (ano, mes) durante `ttl` segundos (GOLD_CACHE_SECONDS).

    O relatório diário e o GET /dashboard pedem o mesmo mês no mesmo processo: o segundo reaproveita o
    resultado em vez de acordar o warehouse de novo."""
    import time

    ttl = GOLD_CACHE_SECONDS if ttl is None else ttl
    hit = _cache.get((ano, mes))
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    gold = load_gold(ano, mes, connect=connect)
    _cache[(ano, mes)] = (time.monotonic(), gold)
    return gold
