"""General settings loaded from .env."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Brasília time (UTC-3, no daylight saving time since 2019). A fixed offset avoids needing the tzdata
# package on Windows. Used for "today" in the prompts ("mês passado") and for the dollar rate day.
BRAZIL_TZ = timezone(timedelta(hours=-3), "BRT")


def today_in_brazil() -> datetime:
    return datetime.now(BRAZIL_TZ)

# --- LangSmith (tracing). The SDK reads the tracing flag and the API key straight from the environment
# (load_dotenv above puts the .env there) and accepts both LANGSMITH_* and LANGCHAIN_* names.
# The project name is a constant, following the NexUs-AI convention (ceris-ms-ia).
os.environ.setdefault("LANGSMITH_PROJECT", "ceris-ms-ia-bi")

# --- LLM
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))  # só para gemini-2.x (o 3.x não aceita temperature)
# Raciocínio do Gemini 3.x (low | medium | high). O padrão do modelo é medium; para chat em tempo real a
# Google recomenda low. Mudar aqui altera latência e custo, não o modelo.
LLM_THINKING_LEVEL = os.getenv("LLM_THINKING_LEVEL", "low").strip().lower()
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))  # limite de cada chamada ao Gemini (o NexUs-AI usa o mesmo)
# Modelo de reserva: se o principal falhar (503 "alta demanda", 429, timeout, rede), a MESMA chamada é refeita
# nele, sem o usuário esperar o limite do principal de novo. Vazio desliga a reserva.
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "gemini-3.5-flash-lite").strip()
# Novas tentativas do SDK em 408/409/429/5xx e falha de conexão. Sem isso o google-genai 2.33 faz até 3 (4
# requisições por chamada, com espera de até 30s, sem log). 0 vale como 1: o SDK não deixa desligar.
# Cada tentativa aparece no log como "gemini.http" (WARNING quando falha).
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))
# Se a resposta citar número que não está nos dados consultados, o agente refaz a resposta até N vezes
MAX_JUDGE_RETRIES = int(os.getenv("MAX_JUDGE_RETRIES", "1"))
# Limite da requisição inteira do chat (o front espera; acima disso devolve erro claro)
CHAT_TIMEOUT_S = float(os.getenv("CHAT_TIMEOUT_S", "120"))

# --- API and authentication (same scheme as NexUs-AI: X-API-Key + Bearer JWT issued by the Auth service)
API_KEY = os.getenv("API_KEY", "")  # key required in the X-API-Key header
# Admin panel key (X-Admin-Key header): the same value in every NexUs service, separate from API_KEY
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
# Daily token cap drawn on the panel's token chart (0 = no cap: Gemini's paid tier has none)
DAILY_TOKEN_LIMIT = int(os.getenv("DAILY_TOKEN_LIMIT", "0"))
JWT_SECRET = os.getenv("JWT_SECRET_BASE64", "")  # same name and value as in the Auth service (Base64)
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "nexus-auth"  # value of the "iss" claim written by the Auth service
# Perfis do token que podem usar o chat (mesma regra de leitura dos relatórios). COMPANY precisa estar ativa.
CHAT_PROFILES = {p.strip().upper() for p in os.getenv("CHAT_PROFILES", "COMPANY,ADMIN").split(",") if p.strip()}
# false = não consulta o Postgres para validar a empresa (só para testes locais; em produção deixe true)
REQUIRE_ACTIVE_COMPANY = os.getenv("CHAT_REQUIRE_ACTIVE_COMPANY", "true").strip().lower() not in ("false", "0", "no")

# --- Qdrant (FAQ)
QDRANT_URL = os.getenv("QDRANT_URL", "")  # use ":memory:" to test without a server
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_FAQ = os.getenv("QDRANT_COLLECTION_FAQ", "faq")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
FAQ_TOP_K = int(os.getenv("FAQ_TOP_K", "4"))  # how many FAQ items go into the prompt
FAQ_PATH = ROOT_DIR / os.getenv("FAQ_PATH", "app/static/faq.json")  # ingestion source

# --- PostgreSQL of the Auth service (only to check that the logged-in company exists and is active)
PGSQL_URL = os.getenv("PGSQL_URL", "")  # postgresql://user:password@host:5432/database

# --- MongoDB (consolidated reports)
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "nexus_bi")
MONGODB_REPORTS_COLLECTION = os.getenv("MONGODB_REPORTS_COLLECTION", "reports")
REPORTS_LATEST_LIMIT = int(os.getenv("REPORTS_LATEST_LIMIT", "3"))  # default for "most recent reports"
REPORTS_MAX_MONTHS = int(os.getenv("REPORTS_MAX_MONTHS", "24"))  # largest period a single search may cover
REPORTS_MAX_CHARS = int(os.getenv("REPORTS_MAX_CHARS", "60000"))  # cap on what one tool call sends to the LLM

# --- Upstash Redis (rankings de produtos)
# REST URL e token do seu projeto em https://console.upstash.com/redis
# Aceita tanto o padrão do projeto (REDIS_REST_*) quanto o nome que o Upstash
# exporta por padrão no dashboard (UPSTASH_REDIS_*).
REDIS_REST_URL = os.getenv("REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL", "")
REDIS_REST_TOKEN = os.getenv("REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN", "")


def validate_config() -> list[str]:
    """List what is missing in .env (empty list = all good)."""
    required = {
        "GOOGLE_API_KEY": GOOGLE_API_KEY,
        "API_KEY": API_KEY,
        "JWT_SECRET_BASE64": JWT_SECRET,
        "QDRANT_URL": QDRANT_URL,
        "MONGODB_URI": MONGODB_URI,
        "PGSQL_URL": PGSQL_URL,
    }
    return [f"Variável ausente no .env: {name}" for name, value in required.items() if not value]
