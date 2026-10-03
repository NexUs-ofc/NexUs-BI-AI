"""Acesso ao FAQ estático (app/static/faq.json).

Formato esperado:
[
  {"pergunta": "...", "resposta": "..."}
]
"""
import json

from app.config import FAQ_PATH


def carregar_faq() -> list[dict]:
    try:
        with open(FAQ_PATH, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []
