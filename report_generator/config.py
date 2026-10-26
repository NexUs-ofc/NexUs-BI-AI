"""Configurações do gerador de relatórios, lidas do mesmo .env da raiz do projeto."""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

BRAZIL_TZ = timezone(timedelta(hours=-3), "BRT")

# --- LangSmith: o projeto do gerador fica separado do chatbot
os.environ.setdefault("LANGSMITH_PROJECT", "ceris-ms-ia-bi-report")

# --- LLM (mesmas variáveis do chatbot)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("REPORT_LLM_MODEL", os.getenv("LLM_MODEL", "gemini-2.5-flash"))
LLM_TEMPERATURE = float(os.getenv("REPORT_LLM_TEMPERATURE", "0.2"))

# --- API e autenticação (mesmo esquema do NexUs-AI: X-API-Key + Bearer JWT do NexUs-Auth)
API_KEY = os.getenv("API_KEY", "")
JWT_SECRET = os.getenv("JWT_SECRET_BASE64", "")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "nexus-auth"
# Perfis que podem LER relatórios e perfis que podem GERAR/PUBLICAR
READ_PROFILES = {p.strip() for p in os.getenv("REPORT_READ_PROFILES", "COMPANY,ADMIN").split(",") if p.strip()}
WRITE_PROFILES = {p.strip() for p in os.getenv("REPORT_WRITE_PROFILES", "ADMIN").split(",") if p.strip()}

# --- MongoDB: o gerador ESCREVE na mesma coleção que o chatbot LÊ
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "nexus_bi")
MONGODB_REPORTS_COLLECTION = os.getenv("MONGODB_REPORTS_COLLECTION", "reports")
MONGODB_JOBS_COLLECTION = os.getenv("MONGODB_REPORT_JOBS_COLLECTION", "report_jobs")

# --- Dados de entrada: "mock" por enquanto; "db" quando a base limpa existir
DATA_SOURCE = os.getenv("REPORT_DATA_SOURCE", "mock")
MOCK_SEED = int(os.getenv("REPORT_MOCK_SEED", "42"))
# Privacidade: grupos (UF) com menos households que isso aparecem como "dados insuficientes"
MIN_HOUSEHOLDS = int(os.getenv("REPORT_MIN_HOUSEHOLDS", "10"))
HISTORY_MONTHS = int(os.getenv("REPORT_HISTORY_MONTHS", "6"))  # meses anteriores lidos do Mongo

# --- PDF: Google Cloud Storage; sem GCS_BUCKET o PDF fica na pasta local REPORT_OUTPUT_DIR
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
GCS_PREFIX = os.getenv("GCS_PREFIX", "relatorios")
OUTPUT_DIR = ROOT_DIR / os.getenv("REPORT_OUTPUT_DIR", "output/relatorios")


def validate_config(use_ai: bool = True) -> list[str]:
    """Lista o que falta no .env para gerar relatórios (lista vazia = tudo certo)."""
    required = {"MONGODB_URI": MONGODB_URI}
    if use_ai:
        required["GOOGLE_API_KEY"] = GOOGLE_API_KEY
    return [f"Variável ausente no .env: {name}" for name, value in required.items() if not value]
