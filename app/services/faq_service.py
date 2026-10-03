"""FAQ service: loads faq.json and indexes it in Qdrant.

Run whenever the FAQ changes (from the project root):
    python -m app.services.faq_service

app/static/faq.json format:
[
  {"question": "...", "answer": "..."}
]
"""
import json

from app.config import FAQ_PATH, QDRANT_COLLECTION_FAQ
from app.repository.faq_repository import index_faq


def load_faq_json() -> list[dict]:
    with open(FAQ_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("faq.json deve ser uma lista de {question, answer}.")
    return [i for i in data if i.get("question") and i.get("answer")]


def reindex_faq() -> int:
    return index_faq(load_faq_json())


if __name__ == "__main__":
    total = reindex_faq()
    print(f"{total} item(ns) do FAQ indexado(s) na collection '{QDRANT_COLLECTION_FAQ}'.")
