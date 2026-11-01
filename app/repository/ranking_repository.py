"""Consultas ao Redis (Upstash) para rankings de produtos.

Utiliza a biblioteca oficial ``upstash-redis`` (REST over HTTP), que não requer
conexão TCP persistente — ideal para ambientes serverless / Upstash.

Chaves consultadas (Sorted Set, ZREVRANGE):
  ranking:product:registered:all        → top 5 produtos mais registrados (geral)
  ranking:product:registered:state:<UF> → top 5 produtos mais registrados por estado
  ranking:product:expired:all           → top 5 produtos mais vencidos (geral)
  ranking:product:expired:state:<UF>    → top 5 produtos mais vencidos por estado
"""
from functools import lru_cache

from upstash_redis import Redis

from app.config import REDIS_REST_TOKEN, REDIS_REST_URL

_TOP_N = 5  # posições retornadas pelo ranking


@lru_cache(maxsize=1)
def _get_redis() -> Redis:
    """Instância única do cliente Redis (Upstash REST)."""
    if not REDIS_REST_URL or not REDIS_REST_TOKEN:
        raise RuntimeError(
            "Variáveis REDIS_REST_URL e/ou REDIS_REST_TOKEN ausentes no .env. "
            "Preencha com os dados do seu projeto Upstash."
        )
    return Redis(url=REDIS_REST_URL, token=REDIS_REST_TOKEN)


def _ranking_key(category: str, state: str | None) -> str:
    """Monta a chave do ZSET conforme a convenção do projeto.

    Args:
        category: ``"registered"`` ou ``"expired"``.
        state: UF em maiúsculas (ex: ``"SP"``). ``None`` para ranking geral.

    Returns:
        Chave Redis, ex: ``"ranking:product:registered:state:SP"`` ou
        ``"ranking:product:registered:all"``.
    """
    suffix = f"state:{state}" if state else "all"
    return f"ranking:product:{category}:{suffix}"


def _zrevrange_with_scores(key: str) -> list[tuple[str, float]]:
    """Executa ZREVRANGE … 0 4 WITHSCORES e devolve lista de (member, score).

    Devolve lista vazia se a chave não existir ou se o Redis estiver indisponível.
    """
    redis = _get_redis()
    # upstash-redis devolve lista de dicts [{"member": ..., "score": ...}]
    # quando WITHSCORES=True
    raw: list[dict] = redis.zrevrange(key, 0, _TOP_N - 1, withscores=True)
    return [(item["member"], float(item["score"])) for item in raw]


def get_registered_ranking(state: str | None = None) -> list[tuple[str, float]]:
    """Top 5 produtos mais registrados, geral ou por UF."""
    return _zrevrange_with_scores(_ranking_key("registered", state))


def get_expired_ranking(state: str | None = None) -> list[tuple[str, float]]:
    """Top 5 produtos mais vencidos, geral ou por UF."""
    return _zrevrange_with_scores(_ranking_key("expired", state))
