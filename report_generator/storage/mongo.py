"""MongoDB: grava o JSON do relatório e lê os relatórios anteriores (histórico).

É a mesma coleção que o chatbot (app/) lê. Um documento por (ano, mes): gerar de novo o mesmo mês
substitui o documento, não duplica.
"""
from datetime import datetime, timezone
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from report_generator.config import (
    MONGODB_DB,
    MONGODB_JOBS_COLLECTION,
    MONGODB_REPORTS_COLLECTION,
    MONGODB_URI,
)

_HIDE_ID = {"_id": 0}


@lru_cache(maxsize=1)
def get_db() -> Database:
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI não definida. Preencha o arquivo .env (veja .env.example).")
    db = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)[MONGODB_DB]
    db[MONGODB_REPORTS_COLLECTION].create_index([("ano", ASCENDING), ("mes", ASCENDING)], unique=True)
    return db


def _reports():
    return get_db()[MONGODB_REPORTS_COLLECTION]


def _jobs():
    return get_db()[MONGODB_JOBS_COLLECTION]


def _period(ano: int, mes: int) -> int:
    return ano * 100 + mes


def save_report(doc: dict) -> None:
    doc = {**doc, "periodo": _period(doc["ano"], doc["mes"])}
    _reports().replace_one({"ano": doc["ano"], "mes": doc["mes"]}, doc, upsert=True)


def find_report(ano: int, mes: int) -> dict | None:
    return _reports().find_one({"ano": ano, "mes": mes}, _HIDE_ID)


def list_reports() -> list[dict]:
    fields = {"_id": 0, "ano": 1, "mes": 1, "status": 1, "gerado_em": 1, "gerado_com_ia": 1, "pdf": 1}
    return list(_reports().find({}, fields).sort([("ano", DESCENDING), ("mes", DESCENDING)]))


def set_status(ano: int, mes: int, status: str) -> bool:
    return _reports().update_one({"ano": ano, "mes": mes}, {"$set": {"status": status}}).matched_count > 0


def set_pdf(ano: int, mes: int, uri: str) -> None:
    pdf = {"uri": uri, "gerado_em": datetime.now(timezone.utc)}
    _reports().update_one({"ano": ano, "mes": mes}, {"$set": {"pdf": pdf}})


def find_previous_dados(ano: int, mes: int, limit: int) -> list[dict]:
    """Só o bloco `dados` dos `limit` meses ANTERIORES a (ano, mes), do mais recente para o mais antigo.

    A narrativa dos meses passados fica de fora de propósito: o histórico usa só números, para um erro
    de interpretação de um mês não se repetir no seguinte.
    """
    query = {"periodo": {"$lt": _period(ano, mes)}}
    fields = {"_id": 0, "ano": 1, "mes": 1, "dados": 1}
    return list(_reports().find(query, fields).sort("periodo", DESCENDING).limit(limit))


# ---------------------------------------------------------------- jobs (status da geração, para a web)
def _job_id(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


def set_job(ano: int, mes: int, status: str, erro: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    update = {"ano": ano, "mes": mes, "status": status, "erro": erro, "atualizado_em": now}
    if status == "em_execucao":
        update["iniciado_em"] = now
    _jobs().update_one({"_id": _job_id(ano, mes)}, {"$set": update}, upsert=True)


def find_job(ano: int, mes: int) -> dict | None:
    return _jobs().find_one({"_id": _job_id(ano, mes)}, _HIDE_ID)
