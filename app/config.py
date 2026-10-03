"""Configurações gerais lidas do .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- LLM
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_TENTATIVAS_JUIZ = int(os.getenv("MAX_TENTATIVAS_JUIZ", "1"))

# --- API
API_KEY = os.getenv("API_KEY", "")  # chave exigida no header X-API-Key

# --- Qdrant (FAQ)
QDRANT_URL = os.getenv("QDRANT_URL", "")  # use ":memory:" para testar sem servidor
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_FAQ = os.getenv("QDRANT_COLLECTION_FAQ", "faq")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
FAQ_LIMITE = int(os.getenv("FAQ_LIMITE", "4"))  # quantos itens do FAQ vão para o prompt
FAQ_PATH = ROOT_DIR / os.getenv("FAQ_PATH", "app/static/faq.json")  # fonte da ingestão


def validar_config() -> list[str]:
    """Lista o que está faltando no .env (vazia = tudo certo)."""
    obrigatorias = {"GOOGLE_API_KEY": GOOGLE_API_KEY, "API_KEY": API_KEY, "QDRANT_URL": QDRANT_URL}
    return [f"Variável ausente no .env: {nome}" for nome, valor in obrigatorias.items() if not valor]
