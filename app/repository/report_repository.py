"""Access to the consolidated reports stored in MongoDB (read-only)."""
from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import MONGODB_DB, MONGODB_REPORTS_COLLECTION, MONGODB_URI

# Field names inside each report document
FIELD_MONTH = "mes"
FIELD_YEAR = "ano"
FIELD_COMPANY = "id_empresa"


@lru_cache(maxsize=1)
def _client() -> MongoClient:
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI não definida. Preencha o arquivo .env (veja .env.example).")
    return MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)


def get_reports_collection() -> Collection:
    return _client()[MONGODB_DB][MONGODB_REPORTS_COLLECTION]


def _company_filter(company_id: str | None) -> list[dict]:
    """Match stage for the company. Accepts the id stored as text or as a number."""
    if not company_id:
        return []
    values: list = [company_id]
    if str(company_id).isdigit():
        values.append(int(company_id))
    return [{"$match": {FIELD_COMPANY: {"$in": values}}}]


# month/year may be saved as int or as text ("09"); $toInt normalizes both so sorting and ranges work.
_PERIOD_FIELDS = {
    "$addFields": {
        "_year": {"$toInt": f"${FIELD_YEAR}"},
        "_month": {"$toInt": f"${FIELD_MONTH}"},
    }
}
_PERIOD_KEY = {"$addFields": {"_period": {"$add": [{"$multiply": ["$_year", 100]}, "$_month"]}}}
_HIDE_HELPERS = {"$project": {"_id": 0, "_year": 0, "_month": 0, "_period": 0}}
_NEWEST_FIRST = {"$sort": {"_year": -1, "_month": -1}}


def find_reports_by_period(
    start_year: int, start_month: int, end_year: int, end_month: int, company_id: str | None = None
) -> list[dict]:
    """Reports whose month/year fall inside [start, end] (inclusive), newest first."""
    start, end = start_year * 100 + start_month, end_year * 100 + end_month
    pipeline = [
        *_company_filter(company_id),
        _PERIOD_FIELDS,
        _PERIOD_KEY,
        {"$match": {"_period": {"$gte": start, "$lte": end}}},
        _NEWEST_FIRST,
        _HIDE_HELPERS,
    ]
    return list(get_reports_collection().aggregate(pipeline))


def find_latest_reports(limit: int, company_id: str | None = None) -> list[dict]:
    """The `limit` most recent reports, newest first."""
    pipeline = [*_company_filter(company_id), _PERIOD_FIELDS, _NEWEST_FIRST, {"$limit": limit}, _HIDE_HELPERS]
    return list(get_reports_collection().aggregate(pipeline))
