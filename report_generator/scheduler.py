"""Geração automática dos relatórios, com IA e PDF.

Roda dentro da API: ao subir o uvicorn, uma tarefa em segundo plano dorme até o próximo horário e gera.
JSON vai para o Mongo e o PDF para o Supabase Storage, como na geração manual.

Dois modos (REPORT_SCHEDULE_FREQUENCY):

- diario (padrão, para testar): todo dia às REPORT_SCHEDULE_HOUR gera o relatório do MÊS ATUAL até hoje
  (marcado `parcial`; sobrescreve o do dia anterior e mantém "publicado" se já estava). Quando o mês vira,
  o primeiro disparo também fecha o mês anterior (regera uma vez, já sem `parcial`).
- mensal: só no dia REPORT_SCHEDULE_DAY gera o mês que acabou (não refaz se já existir).

A Gold do Databricks é atualizada às 07:00 (Brasília) pelo Job_NexUs_BI: mantenha a hora depois disso.
Cada geração faz poucas consultas agregadas numa única conexão (data/databricks.py) por causa da cota da
Free Edition; o resultado fica em cache em memória e é dividido com o GET /dashboard.

Recuperação: ao subir a API, se o horário de hoje já passou e o relatório de hoje ainda não saiu (o servidor
estava desligado), gera na hora.

Hospedagem que desliga a API ociosa (ex.: Cloud Run com mínimo de 0 instâncias): o laço não roda enquanto
ela dorme. Nesse caso agende num cron externo `python -m report_generator.run --diario` (ou `--mes-anterior`).

    REPORT_SCHEDULE_ENABLED=true     liga/desliga o agendador interno
    REPORT_SCHEDULE_FREQUENCY=diario diario | mensal
    REPORT_SCHEDULE_HOUR=8           hora (0 a 23, horário de Brasília)
    REPORT_SCHEDULE_DAY=1            dia do mês (1 a 28), só no modo mensal
    REPORT_AUTO_PUBLISH=false        true = já publica (sem revisão do ADMIN)
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from report_generator import pipeline
from report_generator.config import (
    AUTO_PUBLISH,
    BRAZIL_TZ,
    SCHEDULE_DAY,
    SCHEDULE_ENABLED,
    SCHEDULE_FREQUENCY,
    SCHEDULE_HOUR,
)
from report_generator.storage import mongo

log = logging.getLogger("report_generator")


def previous_month(now: datetime) -> tuple[int, int]:
    return (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)


def previous_month_now() -> tuple[int, int]:
    return previous_month(datetime.now(BRAZIL_TZ))


def _run_time(year: int, month: int) -> datetime:
    return datetime(year, month, SCHEDULE_DAY, SCHEDULE_HOUR, tzinfo=BRAZIL_TZ)


def next_run(now: datetime) -> datetime:
    """Próximo disparo estritamente depois de `now`."""
    now = now.astimezone(BRAZIL_TZ)
    this_month = _run_time(now.year, now.month)
    if now < this_month:
        return this_month
    year, month = (now.year, now.month + 1) if now.month < 12 else (now.year + 1, 1)
    return _run_time(year, month)


def current_month(now: datetime | None = None) -> tuple[int, int]:
    now = (now or datetime.now(BRAZIL_TZ)).astimezone(BRAZIL_TZ)
    return now.year, now.month


def _daily_time(now: datetime) -> datetime:
    return now.astimezone(BRAZIL_TZ).replace(hour=SCHEDULE_HOUR, minute=0, second=0, microsecond=0)


def next_daily_run(now: datetime) -> datetime:
    """Próximo disparo diário estritamente depois de `now`."""
    today = _daily_time(now)
    return today if now.astimezone(BRAZIL_TZ) < today else today + timedelta(days=1)


def run_job(ano: int, mes: int, use_ai: bool = True, publish: bool = False) -> None:
    """Gera um mês registrando o andamento em report_jobs (é o que a web consulta em .../status)."""
    mongo.set_job(ano, mes, "em_execucao")
    try:
        pipeline.run(ano, mes, use_ai=use_ai)
        if publish:
            mongo.set_status(ano, mes, "publicado")
        mongo.set_job(ano, mes, "concluido")
    except Exception as error:
        log.exception("Falha ao gerar %02d/%d", mes, ano)
        mongo.set_job(ano, mes, "erro", erro=f"{type(error).__name__}: {str(error)[:500]}")


def is_running(ano: int, mes: int) -> bool:
    job = mongo.find_job(ano, mes)
    return bool(job and job.get("status") == "em_execucao")


def generate_previous_month(now: datetime | None = None, force: bool = False) -> dict:
    """Gera o mês anterior a `now`, se ainda não existir (force=True gera de novo).

    Devolve o que foi feito, para o log e para a resposta da API."""
    ano, mes = previous_month((now or datetime.now(BRAZIL_TZ)).astimezone(BRAZIL_TZ))
    if is_running(ano, mes):
        return {"ano": ano, "mes": mes, "acao": "ignorado", "motivo": "geração já em andamento"}
    if not force and mongo.find_report(ano, mes):
        return {"ano": ano, "mes": mes, "acao": "ignorado", "motivo": "relatório já existe"}
    log.info("Agendador: gerando o relatório de %02d/%d", mes, ano)
    run_job(ano, mes, use_ai=True, publish=AUTO_PUBLISH)
    return {"ano": ano, "mes": mes, "acao": "gerado", "publicado": AUTO_PUBLISH}


def generate_current_month(now: datetime | None = None) -> dict:
    """Relatório do mês em andamento (parcial). Sempre refaz: os números mudam todo dia."""
    ano, mes = current_month(now)
    if is_running(ano, mes):
        return {"ano": ano, "mes": mes, "acao": "ignorado", "motivo": "geração já em andamento"}
    log.info("Agendador: gerando o relatório parcial de %02d/%d", mes, ano)
    run_job(ano, mes, use_ai=True, publish=AUTO_PUBLISH)
    return {"ano": ano, "mes": mes, "acao": "gerado", "parcial": True, "publicado": AUTO_PUBLISH}


def generate_daily(now: datetime | None = None) -> dict:
    """Disparo diário: fecha o mês anterior se ele ainda não está fechado e atualiza o mês atual.

    O mês anterior só é refeito quando não existe ou foi gerado enquanto ainda estava em andamento
    (`parcial`), então depois de fechado não gasta mais nenhuma consulta no Databricks."""
    now = (now or datetime.now(BRAZIL_TZ)).astimezone(BRAZIL_TZ)
    results = []
    ano, mes = previous_month(now)
    anterior = mongo.find_report(ano, mes)
    if not is_running(ano, mes) and (anterior is None or anterior.get("parcial")):
        log.info("Agendador: fechando o relatório de %02d/%d", mes, ano)
        run_job(ano, mes, use_ai=True, publish=AUTO_PUBLISH)
        results.append({"ano": ano, "mes": mes, "acao": "fechado"})
    results.append(generate_current_month(now))
    return {"acoes": results}


def _ran_today(now: datetime) -> bool:
    """O relatório do mês atual já foi gerado com sucesso hoje (horário de Brasília)?"""
    job = mongo.find_job(*current_month(now))
    stamp = (job or {}).get("atualizado_em")
    if not job or job.get("status") != "concluido" or not isinstance(stamp, datetime):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)  # o Mongo devolve datas sem fuso (UTC)
    return stamp.astimezone(BRAZIL_TZ).date() == now.astimezone(BRAZIL_TZ).date()


async def _sleep_until(target: datetime) -> None:
    # Dorme em blocos de até 1 hora: relógio do servidor ajustado ou suspensão não atrasam o disparo
    while (remaining := (target - datetime.now(BRAZIL_TZ)).total_seconds()) > 0:
        await asyncio.sleep(min(remaining, 3600))


async def scheduler_loop() -> None:
    """Laço da tarefa de fundo da API. A geração roda numa thread para não travar as requisições."""
    now = datetime.now(BRAZIL_TZ)
    if SCHEDULE_FREQUENCY == "diario":
        if now >= _daily_time(now) and not await asyncio.to_thread(_ran_today, now):
            result = await asyncio.to_thread(generate_daily, now)
            log.info("Agendador (recuperação ao iniciar): %s", result)
        while True:
            target = next_daily_run(datetime.now(BRAZIL_TZ))
            log.info("Agendador: próximo relatório diário em %s", target.strftime("%d/%m/%Y %H:%M"))
            await _sleep_until(target)
            try:
                log.info("Agendador: %s", await asyncio.to_thread(generate_daily))
            except Exception:
                log.exception("Agendador: falha inesperada")
    if now >= _run_time(now.year, now.month):
        result = await asyncio.to_thread(generate_previous_month, now)
        log.info("Agendador (recuperação ao iniciar): %s", result)
    while True:
        target = next_run(datetime.now(BRAZIL_TZ))
        log.info("Agendador: próximo relatório em %s", target.strftime("%d/%m/%Y %H:%M"))
        await _sleep_until(target)
        try:
            result = await asyncio.to_thread(generate_previous_month)
            log.info("Agendador: %s", result)
        except Exception:
            log.exception("Agendador: falha inesperada")


def start(loop_factory=scheduler_loop) -> asyncio.Task | None:
    if not SCHEDULE_ENABLED:
        log.info("Agendador desligado (REPORT_SCHEDULE_ENABLED=false)")
        return None
    return asyncio.create_task(loop_factory())
