import mongomock
import pytest

from report_generator.storage import mongo


@pytest.fixture(autouse=True)
def _mock_data_source(monkeypatch):
    """Os testes nunca podem depender do REPORT_DATA_SOURCE do .env de quem roda: se estiver como
    "databricks" (uso normal em produção), qualquer teste que chame pipeline.run()/load_dados() sem passar
    source= explicitamente tentaria conectar de verdade no warehouse — lento, preso a rede/cota, e
    inconsistente entre máquinas. Testes que querem mesmo a Gold (test_databricks.py) passam
    source="databricks" explicitamente e continuam funcionando normalmente."""
    monkeypatch.setattr("report_generator.data.loader.DATA_SOURCE", "mock")


@pytest.fixture(autouse=True)
def _clear_gold_cache():
    from report_generator.data import databricks

    databricks._cache.clear()
    yield
    databricks._cache.clear()


@pytest.fixture
def db(monkeypatch, tmp_path):
    """MongoDB em memória + PDFs numa pasta temporária."""
    database = mongomock.MongoClient()["test"]
    monkeypatch.setattr(mongo, "get_db", lambda: database)
    monkeypatch.setattr("report_generator.storage.files.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("report_generator.storage.files.SUPABASE_URL", "")
    monkeypatch.setattr("report_generator.scheduler.SCHEDULE_ENABLED", False)
    return database
