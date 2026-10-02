"""Configurações gerais lidas do .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
DATA_PATH = ROOT_DIR / os.getenv("DATA_PATH", "app/static/vendas_exemplo.csv")
FAQ_PATH = ROOT_DIR / os.getenv("FAQ_PATH", "app/static/faq.json")
MAX_TENTATIVAS_JUIZ = int(os.getenv("MAX_TENTATIVAS_JUIZ", "1"))
