"""JSON da tela Relatórios do site: os PDFs do bucket, separados por mês.

O índice dos PDFs é o Mongo (cada relatório guarda a URI do seu PDF no Supabase), não uma listagem do
bucket: assim o site não precisa da
chave do Supabase. O PDF em si é entregue por GET /reports/{ano}/{mes}/pdf.

    {"total": 2, "meses": [
        {"id": "2026-09", "ano": 2026, "mes": 9, "titulo": "Setembro 2026", "total": 1,
         "relatorios": [{"id": "2026-09", "titulo": "Desperdício e validade nas despensas", "data": "2026-09-30",
                         "tipo": "Mensal", "status": "publicado", "geradoComIa": true,
                         "geradoEm": "...", "pdf": "/reports/2026/9/pdf",
                         "download": "/reports/2026/9/pdf?download=true"}]}]}
"""
from datetime import datetime

from report_generator.data.loader import last_day

MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
          "Novembro", "Dezembro"]
TITLE = "Desperdício e validade nas despensas"
TYPE = "Mensal"


def _item(r: dict) -> dict:
    ano, mes = r["ano"], r["mes"]
    data = ((r.get("dados") or {}).get("base") or {}).get("data_referencia") or last_day(ano, mes).isoformat()
    gerado = r.get("gerado_em")
    return {
        "id": f"{ano}-{mes:02d}",
        "titulo": TITLE,
        "data": data,
        "tipo": TYPE,
        "status": "publicado",  # não existe mais etapa de rascunho
        "geradoComIa": bool(r.get("gerado_com_ia")),
        "geradoEm": gerado.isoformat() if isinstance(gerado, datetime) else gerado,
        "pdf": f"/reports/{ano}/{mes}/pdf",
        "download": f"/reports/{ano}/{mes}/pdf?download=true",
    }


def merge_bucket(reports: list[dict], pdfs: dict[tuple[int, int], str]) -> list[dict]:
    """Junta o que está no Mongo com o que está no bucket. O bucket manda na existência do PDF: relatório sem
    registro no Mongo (ou sem a URI) entra como publicado, para a tela mostrar TODOS os PDFs."""
    merged = []
    seen = set()
    for r in reports:
        key = (r["ano"], r["mes"])
        seen.add(key)
        merged.append({**r, "pdf": r.get("pdf") or ({"uri": pdfs[key]} if key in pdfs else None)})
    merged.extend({"ano": ano, "mes": mes, "status": "publicado", "pdf": {"uri": uri}}
                  for (ano, mes), uri in pdfs.items() if (ano, mes) not in seen)
    return merged


def group_by_month(reports: list[dict], ano: int | None = None, mes: int | None = None, busca: str | None = None
                   ) -> dict:
    """`reports`: documentos do Mongo + bucket (merge_bucket). Só entram os que já têm PDF; filtra por ano, mês e nome."""
    term = (busca or "").strip().lower()
    groups: dict[tuple[int, int], dict] = {}
    for r in sorted(reports, key=lambda r: (r["ano"], r["mes"]), reverse=True):
        if not r.get("pdf") or (ano and r["ano"] != ano) or (mes and r["mes"] != mes):
            continue
        item = _item(r)
        title = f"{MONTHS[r['mes'] - 1]} {r['ano']}"
        if term and term not in item["titulo"].lower() and term not in title.lower():
            continue
        group = groups.setdefault((r["ano"], r["mes"]), {"id": item["id"], "ano": r["ano"], "mes": r["mes"],
                                                         "titulo": title, "total": 0, "relatorios": []})
        group["relatorios"].append(item)
        group["total"] += 1
    return {"total": sum(g["total"] for g in groups.values()), "meses": list(groups.values())}
