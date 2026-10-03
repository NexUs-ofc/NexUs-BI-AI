"""FAQ access in Qdrant: indexing (ingestion) and similarity search."""
import uuid
from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.config import EMBEDDING_DIM, QDRANT_API_KEY, QDRANT_COLLECTION_FAQ, QDRANT_URL
from app.model.embeddings import embed_text, embed_texts


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    if not QDRANT_URL:
        raise RuntimeError("QDRANT_URL não definida. Preencha o arquivo .env (veja .env.example).")
    if QDRANT_URL == ":memory:":
        return QdrantClient(location=":memory:")
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)


def ensure_collection() -> None:
    qdrant = get_qdrant()
    if not qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION_FAQ,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )


def index_faq(items: list[dict]) -> int:
    """Rebuild the FAQ collection. Each item: {"question": "...", "answer": "..."}."""
    qdrant = get_qdrant()
    if qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        qdrant.delete_collection(QDRANT_COLLECTION_FAQ)
    ensure_collection()
    if not items:
        return 0

    # The vector is built from question + answer, so the search matches both
    vectors = embed_texts([f"{i['question']}\n{i['answer']}" for i in items])
    qdrant.upsert(
        collection_name=QDRANT_COLLECTION_FAQ,
        points=[
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"question": item["question"], "answer": item["answer"]},
            )
            for vector, item in zip(vectors, items)
        ],
    )
    return len(items)


def search_faq(question: str, limit: int) -> list[dict]:
    """Return the FAQ items most similar to the question (empty if the collection does not exist)."""
    qdrant = get_qdrant()
    if not qdrant.collection_exists(QDRANT_COLLECTION_FAQ):
        return []
    result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION_FAQ,
        query=embed_text(question),
        limit=limit,
    )
    return [{**p.payload, "score": round(p.score, 3)} for p in result.points]
