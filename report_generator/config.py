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
# Vazio no .env conta como "não definido": cai no LLM_MODEL do chatbot
LLM_MODEL = os.getenv("REPORT_LLM_MODEL") or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
LLM_TEMPERATURE = float(os.getenv("REPORT_LLM_TEMPERATURE") or "0.2")

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

# --- Dados de entrada: "mock" (desenvolvimento) ou "databricks" (dados limpos, data/databricks.py)
DATA_SOURCE = os.getenv("REPORT_DATA_SOURCE", "mock").strip().lower()
DATABRICKS = {
    "server_hostname": os.getenv("DATABRICKS_SERVER_HOSTNAME", ""),
    "http_path": os.getenv("DATABRICKS_HTTP_PATH", ""),
    "access_token": os.getenv("DATABRICKS_TOKEN", ""),
    "catalog": os.getenv("DATABRICKS_CATALOG", "workspace"),
    "schema": os.getenv("DATABRICKS_SCHEMA", "gold"),
}
# Gold: UF com menos lotes que isso fica fora do ranking e do mapa (amostra pequena distorce o %)
MIN_LOTES_UF = int(os.getenv("REPORT_MIN_LOTES_UF", "30"))
# Horários (de Brasília) em que o GET /dashboard busca a Gold de novo e atualiza o cache em memória; fora
# desses horários devolve o que já tem guardado. A Gold só muda 1x por dia, às 07h (Job_NexUs_BI): o padrão
# 8h/20h garante no máximo 2 buscas por dia por mês pedido, sempre já depois da carga do dia.
DASHBOARD_REFRESH_HOURS = sorted({int(h) for h in os.getenv("REPORT_DASHBOARD_REFRESH_HOURS", "8,20").split(",")})
# Cache em memória da leitura da Gold (por mês pedido). O relatório diário e o /dashboard dividem o mesmo
# resultado, então a Free Edition acorda o warehouse uma vez só.
GOLD_CACHE_SECONDS = int(os.getenv("REPORT_GOLD_CACHE_SECONDS", "1800"))
MOCK_SEED = int(os.getenv("REPORT_MOCK_SEED", "42"))
# Privacidade: grupos (UF) com menos households que isso aparecem como "dados insuficientes"
MIN_HOUSEHOLDS = int(os.getenv("REPORT_MIN_HOUSEHOLDS", "10"))
HISTORY_MONTHS = int(os.getenv("REPORT_HISTORY_MONTHS", "6"))  # meses anteriores lidos do Mongo

# --- PDF: Supabase Storage; sem SUPABASE_URL o PDF fica na pasta local REPORT_OUTPUT_DIR
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")  # só no servidor; nunca no front-end
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "relatorio")
SUPABASE_PREFIX = os.getenv("SUPABASE_PREFIX", "relatorios")
OUTPUT_DIR = ROOT_DIR / os.getenv("REPORT_OUTPUT_DIR", "output/relatorios")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "sim", "yes", "on")


# --- Agendamento (scheduler.py)
#   diario  -> todo dia às SCHEDULE_HOUR gera o relatório do MÊS ATUAL até hoje ("parcial", sobrescreve o do dia
#              anterior) e, quando o mês vira, fecha o anterior. É o modo para testar.
#   mensal  -> só no dia SCHEDULE_DAY gera o mês que acabou.
# O Job do Databricks atualiza a Gold às 07:00 (Brasília): mantenha a hora depois disso.
SCHEDULE_ENABLED = _flag("REPORT_SCHEDULE_ENABLED", "true")
SCHEDULE_FREQUENCY = os.getenv("REPORT_SCHEDULE_FREQUENCY", "diario").strip().lower()
if SCHEDULE_FREQUENCY not in ("diario", "mensal"):
    SCHEDULE_FREQUENCY = "diario"
SCHEDULE_DAY = min(max(int(os.getenv("REPORT_SCHEDULE_DAY", "1")), 1), 28)  # só no modo mensal
SCHEDULE_HOUR = min(max(int(os.getenv("REPORT_SCHEDULE_HOUR", "8")), 0), 23)
SIGNED_URL_SECONDS = int(os.getenv("REPORT_PDF_URL_EXPIRES", "600"))


def validate_config(use_ai: bool = True) -> list[str]:
    """Lista o que falta no .env para gerar relatórios (lista vazia = tudo certo)."""
    required = {"MONGODB_URI": MONGODB_URI}
    if use_ai:
        required["GOOGLE_API_KEY"] = GOOGLE_API_KEY
    if SUPABASE_URL:
        required["SUPABASE_SERVICE_ROLE_KEY"] = SUPABASE_KEY
    if DATA_SOURCE in ("databricks", "db"):
        required["DATABRICKS_SERVER_HOSTNAME"] = DATABRICKS["server_hostname"]
        required["DATABRICKS_HTTP_PATH"] = DATABRICKS["http_path"]
        required["DATABRICKS_TOKEN"] = DATABRICKS["access_token"]
    return [f"Variável ausente no .env: {name}" for name, value in required.items() if not value]
