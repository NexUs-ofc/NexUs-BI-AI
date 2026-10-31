"""Armazenamento dos PDFs: Supabase Storage, ou pasta local quando SUPABASE_URL está vazio (dev).

Usa a API REST do Storage (https://supabase.com/docs/reference/api) com a service role key, que só fica
no servidor. O bucket deve ser PRIVADO: o PDF é entregue pela API do gerador (GET /reports/{ano}/{mes}/pdf),
que confere o perfil do usuário antes. GET /reports lista os PDFs do bucket agrupados por mês (reports_listing.py).

Caminho do arquivo: {SUPABASE_PREFIX}/{ano}/{mes:02d}.pdf  (ex.: relatorios/2026/10.pdf)
URI gravada no Mongo: supabase://{bucket}/{caminho}
"""
from pathlib import Path

import httpx

from report_generator.config import (
    OUTPUT_DIR,
    SUPABASE_BUCKET,
    SUPABASE_KEY,
    SUPABASE_PREFIX,
    SUPABASE_URL,
)

SCHEME = "supabase://"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _name(ano: int, mes: int) -> str:
    return f"{SUPABASE_PREFIX.strip('/')}/{ano}/{mes:02d}.pdf"


def _object_url(bucket: str, name: str) -> str:
    return f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{name}"


def _headers(**extra: str) -> dict:
    """Chaves novas do Supabase (`sb_secret_...`) NÃO são JWT: vão só no header `apikey`. Mandá-las também em
    `Authorization: Bearer` faz o Storage recusar o envio ("Invalid Compact JWS"). Chaves antigas (JWT
    `service_role`, começam com `eyJ`) seguem usando os dois headers."""
    if SUPABASE_KEY.startswith("sb_"):
        return {"apikey": SUPABASE_KEY, **extra}
    return {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, **extra}


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.is_error:
        raise RuntimeError(f"Supabase Storage: falha ao {action} ({response.status_code}): {response.text[:300]}")


def save_pdf(content: bytes, ano: int, mes: int) -> str:
    """Grava o PDF e devolve a URI (supabase://... ou caminho local). Gerar de novo o mês sobrescreve."""
    if SUPABASE_URL:
        name = _name(ano, mes)
        response = httpx.post(
            _object_url(SUPABASE_BUCKET, name),
            content=content,
            headers=_headers(**{"Content-Type": "application/pdf", "x-upsert": "true"}),
            timeout=TIMEOUT,
        )
        _raise_for_status(response, f"enviar {name}")
        return f"{SCHEME}{SUPABASE_BUCKET}/{name}"
    path = OUTPUT_DIR / f"{ano}-{mes:02d}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def split_uri(uri: str) -> tuple[str, str]:
    """supabase://bucket/caminho/arquivo.pdf -> (bucket, caminho/arquivo.pdf)"""
    bucket, _, name = uri.removeprefix(SCHEME).partition("/")
    return bucket, name


def signed_url(uri: str, expires_in: int = 600) -> str | None:
    """URL temporária (assinada) do PDF no bucket privado, para o site abrir direto do Supabase sem passar os
    bytes pela API. None quando o PDF é local (desenvolvimento, sem Supabase)."""
    if not uri.startswith(SCHEME):
        return None
    bucket, name = split_uri(uri)
    response = httpx.post(f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/sign/{bucket}/{name}",
                          json={"expiresIn": int(expires_in)}, headers=_headers(**{"Content-Type": "application/json"}),
                          timeout=TIMEOUT)
    _raise_for_status(response, f"assinar {name}")
    path = response.json().get("signedURL") or response.json().get("signedUrl") or ""
    if not path:
        raise RuntimeError("Supabase Storage: resposta sem signedURL.")
    return path if path.startswith("http") else f"{SUPABASE_URL.rstrip('/')}/storage/v1{path}"


def _list_objects(prefix: str) -> list[dict]:
    response = httpx.post(f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/list/{SUPABASE_BUCKET}",
                          json={"prefix": prefix, "limit": 1000, "offset": 0,
                                "sortBy": {"column": "name", "order": "asc"}},
                          headers=_headers(**{"Content-Type": "application/json"}), timeout=TIMEOUT)
    _raise_for_status(response, f"listar {prefix}")
    return response.json()


def list_pdfs() -> dict[tuple[int, int], str]:
    """Todos os PDFs que existem de fato no bucket (ou na pasta local), por (ano, mês) -> URI.

    É a fonte da tela Relatórios: um PDF que está no Storage aparece mesmo que o Mongo não o conheça."""
    found: dict[tuple[int, int], str] = {}
    if SUPABASE_URL:
        root = SUPABASE_PREFIX.strip("/")
        for folder in _list_objects(root):
            ano = folder.get("name", "")
            if not ano.isdigit():
                continue
            for obj in _list_objects(f"{root}/{ano}"):
                stem, _, ext = obj.get("name", "").rpartition(".")
                if ext == "pdf" and stem.isdigit() and 1 <= int(stem) <= 12:
                    found[(int(ano), int(stem))] = f"{SCHEME}{SUPABASE_BUCKET}/{root}/{ano}/{obj['name']}"
        return found
    for path in OUTPUT_DIR.glob("*-*.pdf") if OUTPUT_DIR.exists() else []:
        ano, _, mes = path.stem.partition("-")
        if ano.isdigit() and mes.isdigit() and 1 <= int(mes) <= 12:
            found[(int(ano), int(mes))] = str(path)
    return found


def load_pdf(uri: str) -> bytes:
    if uri.startswith(SCHEME):
        bucket, _, name = uri.removeprefix(SCHEME).partition("/")
        response = httpx.get(_object_url(bucket, name), headers=_headers(), timeout=TIMEOUT)
        _raise_for_status(response, f"baixar {name}")
        return response.content
    return Path(uri).read_bytes()

