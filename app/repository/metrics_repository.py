"""Metrics of the NexUs BI (web) stored in MongoDB, same database as the reports (db_ceris).

The collections are separate from the ones of NexUs-AI (mobile), so the two apps never mix:
- metrics_bi: one document per question (route, latency, tokens, cost, resolved...)
- tool_metrics_bi: one document per tool call (same format as NexUs-AI's tool_metrics)
Both carry the same trace_id, which links a question to the tools it called.
"""
from datetime import datetime

from pymongo.errors import PyMongoError

from app.config import MONGODB_DB
from app.repository.report_repository import get_mongo_client

METRICS_COLLECTION = "metrics_bi"
TOOL_METRICS_COLLECTION = "tool_metrics_bi"


def _collection(name: str):
    return get_mongo_client()[MONGODB_DB][name]


def save_metric(document: dict) -> None:
    _collection(METRICS_COLLECTION).insert_one(document)


def save_tool_calls(documents: list[dict]) -> None:
    if documents:
        _collection(TOOL_METRICS_COLLECTION).insert_many(documents)


def find_metrics_since(since: datetime) -> list[dict]:
    return list(_collection(METRICS_COLLECTION).find({"created_at": {"$gte": since}}, {"_id": 0}))


def find_tool_calls_since(since: datetime) -> list[dict]:
    return list(_collection(TOOL_METRICS_COLLECTION).find({"started_at": {"$gte": since}}, {"_id": 0}))


def find_metrics_between(since: datetime, until: datetime) -> list[dict]:
    """For the admin panel: an empty list when MongoDB fails, so the page shows zero instead of an error."""
    try:
        query = {"created_at": {"$gte": since, "$lt": until}}
        return list(_collection(METRICS_COLLECTION).find(query, {"_id": 0}))
    except PyMongoError as e:
        print(f"[metrics] ATENÇÃO: não foi possível ler as métricas: {e}")
        return []


def find_tool_calls_between(since: datetime, until: datetime) -> list[dict]:
    try:
        query = {"started_at": {"$gte": since, "$lt": until}}
        return list(_collection(TOOL_METRICS_COLLECTION).find(query, {"_id": 0}))
    except PyMongoError as e:
        print(f"[metrics] ATENÇÃO: não foi possível ler as chamadas de tool: {e}")
        return []
