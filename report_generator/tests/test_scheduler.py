import asyncio
from datetime import datetime

import pytest

from report_generator import scheduler
from report_generator.config import BRAZIL_TZ


def brt(*args) -> datetime:
    return datetime(*args, tzinfo=BRAZIL_TZ)


@pytest.fixture
def fake(monkeypatch):
    """Mongo e pipeline falsos: registra o que o agendador fez, sem banco nem Gemini."""
    state = {"reports": {}, "jobs": {}, "runs": []}

    def run(ano, mes, use_ai=True, with_pdf=True, model=None):
        state["runs"].append((ano, mes, use_ai))
        state["reports"][(ano, mes)] = {"ano": ano, "mes": mes, "status": "publicado"}

    def set_job(ano, mes, status, erro=None):
        state["jobs"][(ano, mes)] = {"status": status, "erro": erro}

    monkeypatch.setattr(scheduler.pipeline, "run", run)
    monkeypatch.setattr(scheduler.mongo, "find_report", lambda a, m: state["reports"].get((a, m)))
    monkeypatch.setattr(scheduler.mongo, "find_job", lambda a, m: state["jobs"].get((a, m)))
    monkeypatch.setattr(scheduler.mongo, "set_job", set_job)
    monkeypatch.setattr(scheduler, "SCHEDULE_DAY", 1)
    monkeypatch.setattr(scheduler, "SCHEDULE_HOUR", 3)
    return state


def test_previous_month():
    assert scheduler.previous_month(brt(2026, 11, 1)) == (2026, 10)
    assert scheduler.previous_month(brt(2027, 1, 1)) == (2026, 12)


def test_next_run(fake):
    assert scheduler.next_run(brt(2026, 10, 26, 9)) == brt(2026, 11, 1, 3)
    assert scheduler.next_run(brt(2026, 11, 1, 2, 59)) == brt(2026, 11, 1, 3)
    assert scheduler.next_run(brt(2026, 11, 1, 3)) == brt(2026, 12, 1, 3)
    assert scheduler.next_run(brt(2026, 12, 5)) == brt(2027, 1, 1, 3)


def test_generates_previous_month_with_ai_once(fake):
    result = scheduler.generate_previous_month(brt(2026, 11, 1, 3))
    assert result["acao"] == "gerado" and (result["ano"], result["mes"]) == (2026, 10)
    assert fake["runs"] == [(2026, 10, True)]
    assert fake["jobs"][(2026, 10)]["status"] == "concluido"
    assert fake["reports"][(2026, 10)]["status"] == "publicado"

    # Já existe: não refaz (não refaz sem necessidade)
    again = scheduler.generate_previous_month(brt(2026, 11, 1, 4))
    assert again["acao"] == "ignorado" and len(fake["runs"]) == 1
    # force=True refaz
    scheduler.generate_previous_month(brt(2026, 11, 1, 4), force=True)
    assert len(fake["runs"]) == 2


def test_skips_when_already_running(fake):
    fake["jobs"][(2026, 10)] = {"status": "em_execucao"}
    assert scheduler.generate_previous_month(brt(2026, 11, 1, 3))["acao"] == "ignorado"
    assert fake["runs"] == []


def test_failure_is_recorded_in_job(fake, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("Gemini fora do ar")

    monkeypatch.setattr(scheduler.pipeline, "run", boom)
    scheduler.generate_previous_month(brt(2026, 11, 1, 3))
    job = fake["jobs"][(2026, 10)]
    assert job["status"] == "erro" and "Gemini fora do ar" in job["erro"]


def test_start_respects_enabled_flag(monkeypatch):
    async def noop():
        return None

    async def main():
        monkeypatch.setattr(scheduler, "SCHEDULE_ENABLED", False)
        assert scheduler.start(noop) is None
        monkeypatch.setattr(scheduler, "SCHEDULE_ENABLED", True)
        task = scheduler.start(noop)
        await task

    asyncio.run(main())


def test_cli_previous_month_uses_scheduler_rule(monkeypatch):
    """`run --mes-anterior` (o que um cron externo chama) segue a regra do agendador: não refaz o mês."""
    from report_generator import run

    calls = []
    monkeypatch.setattr(run, "validate_config", lambda use_ai=True: [])
    monkeypatch.setattr(run, "generate_previous_month",
                        lambda force=False: calls.append(force) or {"ano": 2026, "mes": 10, "acao": "ignorado"})
    monkeypatch.setattr(run.mongo, "find_job", lambda a, m: None)
    assert run.main(["--mes-anterior"]) == 0
    assert run.main(["--mes-anterior", "--forcar"]) == 0
    assert calls == [False, True]
