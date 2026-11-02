"""Logs estruturados do chat, para acompanhar no terminal cada etapa de uma requisição.

Cada linha traz o id da requisição (req=...), a etapa e os campos chave=valor:

    01:30:00.120 INFO  [req=3f2a9c1b] requisicao.inicio metodo=POST rota=/chat
    01:30:00.410 INFO  [req=3f2a9c1b] auth.postgres.fim ms=289.7 perfil=COMPANY
    01:30:02.950 INFO  [req=3f2a9c1b] gemini.chamada.fim ms=2531.0 modelo=gemini-3.8-flash tokens_in=1830 ...
    01:30:03.020 INFO  [req=3f2a9c1b] requisicao.fim status=200 total_ms=2900.1 gemini_ms=2531.0(1x) ...

- `step(...)` mede uma etapa: loga início, fim (ou ERRO) e o tempo em ms. Com `service=...` o tempo também
  entra na soma por serviço externo (gemini, gemini_embedding, mongodb, qdrant, postgres).
- O resumo do fim da requisição separa o tempo de cada serviço externo e o que sobra ("backend_ms"), para
  mostrar se o gargalo é o Gemini, o MongoDB, o Qdrant ou o próprio código.

Nada sensível vai para o log: nunca o texto da pergunta/resposta (só o tamanho), nunca chaves, tokens
ou senhas. `redact()` limpa mensagens de erro de bibliotecas antes de logar ou devolver ao usuário.

Nível do log: LOG_LEVEL no .env (INFO por padrão; DEBUG mostra cada tentativa HTTP ao Gemini).
"""
import contextvars
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager

logger = logging.getLogger("nexus.chat")

# Serviços externos somados no resumo da requisição (ordem de exibição)
EXTERNAL_SERVICES = ("gemini", "gemini_embedding", "mongodb", "qdrant", "postgres")

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(key|token|secret|password|senha|apikey|api_key)=([^&\s\"']+)"), r"\1=***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+"), r"\1 ***"),
    (re.compile(r"(?i)(x-goog-api-key|x-api-key|authorization)[\"']?\s*[:=]\s*[\"']?[^\s,\"'}]+"), r"\1: ***"),
    (re.compile(r"([a-z][a-z0-9+.\-]*://)[^:/@\s]+:[^@\s]+@"), r"\1***:***@"),  # mongodb+srv://user:pass@
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}"), "***"),  # chave clássica do Google
    (re.compile(r"\bAQ\.[0-9A-Za-z_\-.]{20,}"), "***"),  # chave nova do Google AI Studio
    (re.compile(r"\beyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]+"), "***"),  # JWT
]


def redact(text: object, limit: int = 300) -> str:
    """Remove credenciais de um texto (mensagens de erro de SDKs podem trazer URL, header ou chave)."""
    value = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    value = " ".join(value.split())  # uma linha só
    return value if len(value) <= limit else value[:limit] + "..."


class RequestTrace:
    """Tempos de uma requisição, compartilhados por todas as etapas (inclusive as que rodam em thread)."""

    def __init__(self) -> None:
        self.request_id = uuid.uuid4().hex[:8]
        self.started = time.perf_counter()
        self.external_ms: dict[str, float] = defaultdict(float)
        self.external_calls: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def add(self, service: str, ms: float) -> None:
        with self._lock:
            self.external_ms[service] += ms
            self.external_calls[service] += 1

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000

    def summary(self) -> dict:
        """Tempo total, tempo de cada serviço externo e o resto (código do backend, fila de threads...)."""
        total = self.elapsed_ms()
        fields: dict = {"total_ms": round(total, 1)}
        external = 0.0
        for service in EXTERNAL_SERVICES:
            if self.external_calls.get(service):
                ms = self.external_ms[service]
                external += ms
                fields[f"{service}_ms"] = f"{ms:.1f}({self.external_calls[service]}x)"
        fields["backend_ms"] = round(total - external, 1)
        return fields


_current: contextvars.ContextVar[RequestTrace | None] = contextvars.ContextVar("chat_request_trace", default=None)


def start_request() -> RequestTrace:
    trace = RequestTrace()
    _current.set(trace)
    return trace


def current() -> RequestTrace | None:
    return _current.get()


def attach(request_trace: RequestTrace | None) -> None:
    """Use the trace of a request in another thread (e.g. a background task started by it)."""
    _current.set(request_trace)


def _format(fields: dict) -> str:
    parts = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        if isinstance(value, float):
            value = round(value, 1)
        parts.append(f"{key}={value}")
    return " ".join(parts)


def log(event: str, level: int = logging.INFO, **fields) -> None:
    trace = current()
    prefix = f"[req={trace.request_id}] " if trace else ""
    logger.log(level, "%s%s %s", prefix, event, _format(fields))


@contextmanager
def step(name: str, service: str | None = None, **fields):
    """Mede uma etapa. O bloco pode preencher o dicionário devolvido com campos do resultado:

        with step("mongodb.relatorios", service="mongodb", periodo="2026-09") as info:
            reports = find(...)
            info["documentos"] = len(reports)
    """
    log(f"{name}.inicio", **fields)
    info: dict = {}
    started = time.perf_counter()
    try:
        yield info
    except Exception as error:
        ms = (time.perf_counter() - started) * 1000
        if service and (trace := current()):
            trace.add(service, ms)
        log(f"{name}.ERRO", logging.ERROR, ms=ms, **fields, erro=type(error).__name__, detalhe=redact(error))
        raise
    ms = (time.perf_counter() - started) * 1000
    if service and (trace := current()):
        trace.add(service, ms)
    log(f"{name}.fim", ms=ms, **fields, **info)


def configure_logging() -> None:
    """Handler próprio no terminal (uvicorn não mexe nele). Chamado uma vez ao subir a API."""
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-5s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
