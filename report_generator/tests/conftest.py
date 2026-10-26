import mongomock
import pytest

from report_generator.storage import mongo


@pytest.fixture
def db(monkeypatch, tmp_path):
    """MongoDB em memória + PDFs numa pasta temporária."""
    database = mongomock.MongoClient()["test"]
    monkeypatch.setattr(mongo, "get_db", lambda: database)
    monkeypatch.setattr("report_generator.storage.files.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("report_generator.storage.files.GCS_BUCKET", "")
    return database
