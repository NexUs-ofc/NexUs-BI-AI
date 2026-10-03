"""Acesso ao FAQ no Qdrant: indexar (ingestão) e buscar por similaridade."""
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.config import EMBEDDING_DIM, QDRANT_API_KEY, QDRANT_COLLECTION_FAQ, QDRANT_URL
from app.model.embeddings import gerar_embedding, gerar_embeddings


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    if not QDRANT_URL:
        raise RuntimeError("QDRANT_URL não definida. Preencha o arquivo .env (veja .env.example).")
    if QDRANT_URL == ":memory:":
        return QdrantClient(location=":memory:")
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)


def garantir_collection() -> None:
    qdrant = get_qdrant()
    if not qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION_FAQ,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )


def indexar_faq(itens: list[dict]) -> int:
    """Recria o FAQ na collection. Cada item: {"pergunta": "...", "resposta": "..."}."""
    qdrant = get_qdrant()
    if qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        qdrant.delete_collection(QDRANT_COLLECTION_FAQ)
    garantir_collection()
    if not itens:
        return 0

    # O vetor é gerado a partir de pergunta + resposta, para a busca achar pelos dois
    textos = [f"{i['pergunta']}\n{i['resposta']}" for i in itens]
    vetores = gerar_embeddings(textos)
    qdrant.upsert(
        collection_name=QDRANT_COLLECTION_FAQ,
        points=[
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vetor,
                payload={"pergunta": item["pergunta"], "resposta": item["resposta"]},
            )
            for vetor, item in zip(vetores, itens)
        ],
    )
    return len(itens)


def buscar_faq(pergunta: str, limite: int) -> list[dict]:
    """Devolve os itens do FAQ mais parecidos com a pergunta (vazio se a collection não existir)."""
    qdrant = get_qdrant()
    if not qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        return []
    resultado = qdrant.query_points(
        collection_name=QDRANT_COLLECTION_FAQ,
        query=gerar_embedding(pergunta),
        limit=limite,
    )
    return [{**p.payload, "score": round(p.score, 3)} for p in resultado.points]
