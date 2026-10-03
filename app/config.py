"""General settings loaded from .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- LLM
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
MAX_JUDGE_RETRIES = int(os.getenv("MAX_JUDGE_RETRIES", "1"))

# --- API
API_KEY = os.getenv("API_KEY", "")  # key required in the X-API-Key header

# --- Qdrant (FAQ)
QDRANT_URL = os.getenv("QDRANT_URL", "")  # use ":memory:" to test without a server
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_FAQ = os.getenv("QDRANT_COLLECTION_FAQ", "faq")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
FAQ_TOP_K = int(os.getenv("FAQ_TOP_K", "4"))  # how many FAQ items go into the prompt
FAQ_PATH = ROOT_DIR / os.getenv("FAQ_PATH", "app/static/faq.json")  # ingestion source


def validate_config() -> list[str]:
    """List what is missing in .env (empty list = all good)."""
    required = {"GOOGLE_API_KEY": GOOGLE_API_KEY, "API_KEY": API_KEY, "QDRANT_URL": QDRANT_URL}
    return [f"Variável ausente no .env: {name}" for name, value in required.items() if not value]
