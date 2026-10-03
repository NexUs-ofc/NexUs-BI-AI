"""Service de FAQ: carrega o faq.json e indexa no Qdrant.

Rodar sempre que o FAQ mudar (na raiz do projeto):
    python -m app.services.faq_service

Formato do app/static/faq.json:
[
  {"pergunta": "...", "resposta": "..."}
]
"""
import json

from app.config import FAQ_PATH, QDRANT_COLLECTION_FAQ
from app.repository.faq_repository import indexar_faq


def carregar_faq_json() -> list[dict]:
    with open(FAQ_PATH, encoding="utf-8") as f:
        dados = json.load(f)
    if not isinstance(dados, list):
        raise ValueError("faq.json deve ser uma lista de {pergunta, resposta}.")
    return [i for i in dados if i.get("pergunta") and i.get("resposta")]


def reindexar_faq() -> int:
    return indexar_faq(carregar_faq_json())


if __name__ == "__main__":
    total = reindexar_faq()
    print(f"{total} item(ns) do FAQ indexado(s) na collection '{QDRANT_COLLECTION_FAQ}'.")
