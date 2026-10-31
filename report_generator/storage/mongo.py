"""MongoDB: grava o JSON do relatório e lê os relatórios anteriores (histórico).

Só DUAS coleções pertencem ao gerador (nomes no .env):
- MONGODB_REPORTS_COLLECTION (padrão `reports`)          um documento por (ano, mes): o JSON do relatório.
                                                         É a mesma coleção que o chatbot (app/) lê.
- MONGODB_REPORT_JOBS_COLLECTION (padrão `report_jobs`)  um documento por (ano, mes): andamento da geração.

Gerar de novo o mesmo mês substitui o documento (não duplica). Qualquer outra coleção que apareça no banco
(ex.: `reports_mock`) não é usada por este código: `python -m report_generator.diagnostico` lista todas.
"""
import logging
from datetime import UTC, datetime
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from report_generator.config import (
    MONGODB_DB,
    MONGODB_JOBS_COLLECTION,
    MONGODB_REPORTS_COLLECTION,
    MONGODB_URI,
)

log = logging.getLogger("report_generator")

_HIDE_ID = {"_id": 0}
JOB_HISTORY = 20  # quantas execuções ficam registradas dentro do documento do job


@lru_cache(maxsize=1)
def get_db() -> Database:
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI não definida. Preencha o arquivo .env (veja .env.example).")
    db = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)[MONGODB_DB]
    try:
        db[MONGODB_REPORTS_COLLECTION].create_index([("ano", ASCENDING), ("mes", ASCENDING)], unique=True)
    except Exception as error:  # noqa: BLE001
        # Documento antigo duplicado (ou com ano/mes em outro tipo) impede o índice único. Isso NÃO pode
        # derrubar a geração: o save_report usa upsert por (ano, mes), então não duplica mesmo sem o índice.
        log.warning("Não foi possível criar o índice único (ano, mes) em '%s': %s", MONGODB_REPORTS_COLLECTION,
                    error)
    return db


def _reports():
    return get_db()[MONGODB_REPORTS_COLLECTION]


def _jobs():
    return get_db()[MONGODB_JOBS_COLLECTION]


def _period(ano: int, mes: int) -> int:
    return ano * 100 + mes


def save_report(doc: dict) -> None:
    """Grava (ou substitui) o relatório do mês e CONFERE o resultado: se o Mongo não confirmar a gravação,
    levanta erro em vez de seguir como se tivesse salvo."""
    doc = {**doc, "periodo": _period(doc["ano"], doc["mes"])}
    result = _reports().replace_one({"ano": doc["ano"], "mes": doc["mes"]}, doc, upsert=True)
    if not result.acknowledged or not (result.matched_count or result.upserted_id):
        raise RuntimeError(f"MongoDB não confirmou a gravação do relatório {doc['mes']:02d}/{doc['ano']} "
                           f"na coleção '{MONGODB_REPORTS_COLLECTION}'.")
    log.info("Relatório %02d/%d gravado em %s.%s (%s)", doc["mes"], doc["ano"], MONGODB_DB,
             MONGODB_REPORTS_COLLECTION, "criado" if result.upserted_id else "substituído")


def find_report(ano: int, mes: int) -> dict | None:
    return _reports().find_one({"ano": ano, "mes": mes}, _HIDE_ID)


def list_reports() -> list[dict]:
    fields = {"_id": 0, "ano": 1, "mes": 1, "status": 1, "gerado_em": 1, "gerado_com_ia": 1, "pdf": 1,
              "parcial": 1, "dados.base.data_referencia": 1}
    return list(_reports().find({}, fields).sort([("ano", DESCENDING), ("mes", DESCENDING)]))


def set_status(ano: int, mes: int, status: str) -> bool:
    return _reports().update_one({"ano": ano, "mes": mes}, {"$set": {"status": status}}).matched_count > 0


def set_pdf(ano: int, mes: int, uri: str) -> None:
    pdf = {"uri": uri, "gerado_em": datetime.now(UTC)}
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
    """Atualiza o job do mês (1 documento por mês) e guarda as últimas execuções em `historico`."""
    now = datetime.now(UTC)
    update = {"ano": ano, "mes": mes, "status": status, "erro": erro, "atualizado_em": now}
    if status == "em_execucao":
        update["iniciado_em"] = now
    entry = {"status": status, "em": now, "erro": erro}
    _jobs().update_one({"_id": _job_id(ano, mes)},
                       {"$set": update, "$push": {"historico": {"$each": [entry], "$slice": -JOB_HISTORY}}},
                       upsert=True)


def find_job(ano: int, mes: int) -> dict | None:
    return _jobs().find_one({"_id": _job_id(ano, mes)}, _HIDE_ID)
