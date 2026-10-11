"""Embeddings factory (used to index and search the FAQ in Qdrant)."""
from functools import lru_cache

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, GOOGLE_API_KEY


@lru_cache(maxsize=1)
def _embeddings() -> GoogleGenerativeAIEmbeddings:
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY não definida. Preencha o arquivo .env (veja .env.example).")
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, google_api_key=GOOGLE_API_KEY)


def embed_text(text: str) -> list[float]:
    return _embeddings().embed_query(text, output_dimensionality=EMBEDDING_DIM)


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _embeddings().embed_documents(texts, output_dimensionality=EMBEDDING_DIM)
