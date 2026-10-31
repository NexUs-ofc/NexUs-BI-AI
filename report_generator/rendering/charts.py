"""Gráficos do relatório em SVG puro, gerados em Python.

Sem JavaScript nem CDN: o mesmo SVG aparece igual na prévia HTML e no PDF do Chromium, e o PDF não
depende de rede. Cada função recebe pedaços do JSON do relatório e devolve uma string <svg>, que o
template insere com o filtro |safe.

Paleta roxa do Ceris (mesma do site): série 1 roxo escuro, série 2 lilás; a meta é sempre a linha
tracejada dourada; status (bom/alerta/crítico) são reservados para meta e aparecem junto de um rótulo.
"""
import itertools
from html import escape

from report_generator.formatting import br, integer, pct

SERIES_1 = "#4b1d7a"  # roxo do Ceris
SERIES_2 = "#9677b4"  # lilás
SURFACE = "#ffffff"
INK = "#1f1a2e"
INK_2 = "#6b6478"
GRID = "#ebe6f2"
TRACK = "#f1ecf8"
META = "#b08a2e"  # dourado da linha de meta
STATUS_COLOR = {"dentro_meta": "#2e8b57", "acima_da_meta": "#c0392b", "alerta": "#d4a017"}
FONT = "font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif"
MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

BAR_H = 14  # espessura das barras (fino; o resto da faixa fica de respiro)
RADIUS = 4  # ponta arredondada só na extremidade do dado


def _svg(width: int, height: int, body: str, label: str) -> str:
    return (f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" role="img" '
            f'aria-label="{escape(label)}" xmlns="http://www.w3.org/2000/svg" style="{FONT}">{body}</svg>')


def _text(x, y, text, size=10, color=INK_2, anchor="start", weight=400) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{escape(str(text))}</text>')


def _hbar(x: float, y: float, length: float, h: float, color: str) -> str:
    """Barra horizontal com o canto arredondado só na ponta (base reta, presa ao eixo)."""
    if length <= 0:
        return ""
    r = min(RADIUS, length, h / 2)
    return (f'<path d="M{x:.1f},{y:.1f} h{length - r:.1f} a{r},{r} 0 0 1 {r},{r} v{h - 2 * r:.1f} '
            f'a{r},{r} 0 0 1 {-r},{r} h{-(length - r):.1f} z" fill="{color}"/>')


def _nice_max(value: float) -> float:
    """Arredonda o topo da escala para um número "redondo" (1, 2, 2,5, 5 x 10^n)."""
    if value <= 0:
        return 1.0
    exp = 10 ** (len(str(int(value))) - 1) if value >= 1 else 0.1
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp


def _clip(text: str, chars: int) -> str:
    return text if len(text) <= chars else text[: chars - 1] + "…"


# ---------------------------------------------------------------- KPI x meta (dentro dos cards)
def kpi_meter(kpi: dict) -> str:
    """Trilha com o valor do KPI e um traço na meta. Cor = status (o card já mostra o rótulo)."""
    valor, meta = kpi.get("valor"), kpi.get("meta")
    if valor is None:
        return ""
    w, h = 140, 22
    top = _nice_max(max(valor, meta or 0) * 1.15)
    scale = w / top
    color = STATUS_COLOR.get(kpi.get("status"), SERIES_1)
    body = f'<rect x="0" y="6" width="{w}" height="8" rx="4" fill="{TRACK}"/>'
    body += _hbar(0, 6, valor * scale, 8, color)
    if meta is not None:
        mx = meta * scale
        body += f'<line x1="{mx:.1f}" x2="{mx:.1f}" y1="2" y2="18" stroke="{META}" stroke-width="2"/>'
    return _svg(w, h, body, f"{kpi['codigo']}: {pct(valor)} contra meta de {pct(meta)}")


# ---------------------------------------------------------------- evolução mensal (small multiples)
def kpi_trends(report: dict, history: list[dict] | None, codes: list[str]) -> str:
    """Um minigráfico de linha por KPI: últimos meses + o atual, com a meta tracejada.

    `history` vem de mongo.find_previous_dados (mais recente primeiro). Sem histórico não há tendência,
    então devolve string vazia e o template esconde a seção.
    """
    months = list(reversed(history or [])) + [{"ano": report["ano"], "mes": report["mes"], "dados": report["dados"]}]
    if len(months) < 2:
        return ""
    cols, cell_w, cell_h, gap = len(codes), 128, 120, 12
    width = cols * cell_w + (cols - 1) * gap
    pad_l, pad_r, pad_t, pad_b = 6, 10, 40, 20
    plot_w, plot_h = cell_w - pad_l - pad_r, cell_h - pad_t - pad_b
    n = len(months)
    body = ""
    for i, code in enumerate(codes):
        ox = i * (cell_w + gap)
        values = [m["dados"].get("kpis", {}).get(code, {}).get("valor") for m in months]
        kpi = report["dados"]["kpis"][code]
        meta = kpi.get("meta")
        # Escala ajustada aos dados (não começa no zero): o objetivo aqui é mostrar a variação mês a mês
        known = [v for v in values if v is not None] + ([meta] if meta is not None else [])
        if not known:
            continue
        lo, hi = min(known), max(known)
        span = max(hi - lo, 1.0)
        lo, hi = lo - span * 0.25, hi + span * 0.25

        def px(j, _ox=ox):
            return _ox + pad_l + (plot_w * j / (n - 1))

        def py(v, _lo=lo, _hi=hi):
            return pad_t + plot_h - (v - _lo) / (_hi - _lo) * plot_h

        body += _text(ox, 11, code, 9.5, INK, weight=700) + _text(ox + 22, 11, _clip(kpi["nome"], 20), 9, INK_2)
        if meta is not None:
            y = py(meta)
            body += (f'<line x1="{ox + pad_l}" x2="{ox + pad_l + plot_w}" y1="{y:.1f}" y2="{y:.1f}" stroke="{META}" '
                     f'stroke-width="1.5" stroke-dasharray="4 3"/>')
            body += (f'<line x1="{ox}" x2="{ox + 14}" y1="22" y2="22" stroke="{META}" stroke-width="1.5" '
                     f'stroke-dasharray="4 3"/>') + _text(ox + 18, 25, f"meta até {br(meta, 0)}%", 8)
        pts = [(px(j), py(v)) for j, v in enumerate(values) if v is not None]
        if len(pts) >= 2:
            path = " ".join(f"{'M' if k == 0 else 'L'}{x:.1f},{y:.1f}" for k, (x, y) in enumerate(pts))
            body += (f'<path d="{path}" fill="none" stroke="{SERIES_1}" stroke-width="2" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        if values[-1] is not None:
            x, y = px(n - 1), py(values[-1])
            body += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{SERIES_1}" stroke="{SURFACE}" stroke-width="2"/>'
            label_y = y - 8 if y - 8 > pad_t - 2 else y + 15
            body += _text(x, label_y, pct(values[-1]), 9, INK, "end", 600)
        first, last = months[0], months[-1]
        body += (f'<line x1="{ox + pad_l}" x2="{ox + pad_l + plot_w}" y1="{pad_t + plot_h + 4}" '
                 f'y2="{pad_t + plot_h + 4}" stroke="{GRID}" stroke-width="1"/>')
        body += _text(ox + pad_l, cell_h - 4, f"{MONTHS_SHORT[first['mes'] - 1]}/{str(first['ano'])[2:]}", 8)
        body += _text(ox + pad_l + plot_w, cell_h - 4, f"{MONTHS_SHORT[last['mes'] - 1]}/{str(last['ano'])[2:]}",
                      8, anchor="end")
    return _svg(width, cell_h, body, "Evolução mensal dos indicadores contra a meta")


# ---------------------------------------------------------------- barras horizontais
def _hbars(rows: list[tuple[str, float, str]], width: int, label_w: int, title: str,
           value_fmt=lambda v: br(v, 0), color: str = SERIES_1, ref: tuple[float, str] | None = None) -> str:
    """Barras horizontais ordenadas: (rótulo, valor, texto do valor). `ref` = linha de referência."""
    if not rows:
        return ""
    row_h, pad_t = 22, 4
    top = _nice_max(max(max(v for _, v, _ in rows), ref[0] if ref else 0) * 1.08)
    plot_w = width - label_w - 48
    height = pad_t + len(rows) * row_h + (14 if ref else 4)
    body = ""
    for i, (label, value, text) in enumerate(rows):
        y = pad_t + i * row_h
        body += _text(label_w - 8, y + row_h / 2 + 3.5, _clip(label, int(label_w / 5.4)), 9.5, INK, "end")
        length = value / top * plot_w
        body += _hbar(label_w, y + (row_h - BAR_H) / 2, length, BAR_H, color)
        body += _text(label_w + length + 5, y + row_h / 2 + 3.5, text or value_fmt(value), 9, INK)
    body = (f'<line x1="{label_w}" x2="{label_w}" y1="{pad_t - 2}" y2="{pad_t + len(rows) * row_h}" '
            f'stroke="{INK_2}" stroke-width="1"/>') + body
    if ref:
        x = label_w + ref[0] / top * plot_w
        bottom = pad_t + len(rows) * row_h
        body += (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t - 2}" y2="{bottom}" stroke="{META}" stroke-width="1.5" '
                 f'stroke-dasharray="4 3"/>')
        body += _text(x, bottom + 11, ref[1], 8, INK_2, "middle")
    return _svg(width, height, body, title)


def evolucao_desperdicio(pontos: list[dict], meta: float | None) -> str:
    """Linhas dos últimos meses: taxa de desperdício (roxo) e descarte por esquecimento (lilás), meta tracejada.

    `pontos`: [{ano_mes: "2026-10", d1, d2, completo}] em ordem cronológica. O mês em andamento (completo=False)
    aparece com o ponto vazado e a linha tracejada até ele, para ninguém ler um mês parcial como fechado."""
    pontos = [p for p in pontos if p.get("d1") is not None or p.get("d2") is not None]
    if len(pontos) < 2:
        return ""
    w, h, pad_l, pad_r, pad_t, pad_b = 680, 200, 38, 24, 30, 28
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    valores = [v for p in pontos for v in (p.get("d1"), p.get("d2")) if v is not None] + ([meta] if meta else [])
    top = _nice_max(max(valores) * 1.15)
    n = len(pontos)

    def px(i):
        return pad_l + plot_w * i / (n - 1)

    def py(v):
        return pad_t + plot_h - v / top * plot_h

    body = ""
    for tick in range(5):
        v = top * tick / 4
        body += (f'<line x1="{pad_l}" x2="{pad_l + plot_w}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="{GRID}" '
                 f'stroke-width="1"/>' + _text(pad_l - 6, py(v) + 3, f"{br(v, 0)}%", 8.5, INK_2, "end"))
    if meta:
        body += (f'<line x1="{pad_l}" x2="{pad_l + plot_w}" y1="{py(meta):.1f}" y2="{py(meta):.1f}" stroke="{META}" '
                 f'stroke-width="1.5" stroke-dasharray="5 4"/>'
                 + _text(pad_l + plot_w, py(meta) - 4, f"meta {br(meta, 0)}%", 8.5, META, "end", 600))
    for key, color in (("d1", SERIES_1), ("d2", SERIES_2)):
        pts = [(i, p[key]) for i, p in enumerate(pontos) if p.get(key) is not None]
        for (i0, v0), (i1, v1) in itertools.pairwise(pts):
            dash = '' if pontos[i1].get("completo", True) else ' stroke-dasharray="5 4"'
            body += (f'<line x1="{px(i0):.1f}" y1="{py(v0):.1f}" x2="{px(i1):.1f}" y2="{py(v1):.1f}" '
                     f'stroke="{color}" stroke-width="2.4" stroke-linecap="round"{dash}/>')
        for i, v in pts:
            vazado = not pontos[i].get("completo", True)
            fill = SURFACE if vazado else color
            body += (f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="4" fill="{fill}" stroke="{color}" '
                     f'stroke-width="2"/>' + _text(px(i), py(v) - 9, pct(v), 8.5, INK, "middle", 600))
    for i, p in enumerate(pontos):
        ano, mes = p["ano_mes"].split("-")
        rotulo = f"{MONTHS_SHORT[int(mes) - 1]}/{ano[2:]}" + ("*" if not p.get("completo", True) else "")
        body += _text(px(i), h - 8, rotulo, 9, INK_2, "middle")
    body += (f'<rect x="{pad_l}" y="6" width="10" height="10" rx="2" fill="{SERIES_1}"/>'
             + _text(pad_l + 15, 15, "Taxa de desperdício", 9, INK)
             + f'<rect x="{pad_l + 120}" y="6" width="10" height="10" rx="2" fill="{SERIES_2}"/>'
             + _text(pad_l + 135, 15, "Descarte por esquecimento", 9, INK))
    if any(not p.get("completo", True) for p in pontos):
        body += _text(pad_l + plot_w, 15, "* mês em andamento", 8.5, INK_2, "end")
    return _svg(w, h, body, "Evolução da taxa de desperdício e do descarte por esquecimento")


def desperdicio_por_categoria(rows: list[dict], limit: int = 8) -> str:
    """Unidades descartadas por casa (desperdício da categoria no mês), com a participação no total."""
    top = [r for r in rows if r.get("d9_indice") is not None and r["unidades_descartadas"] > 0][:limit]
    return _hbars([(r["categoria"], r["d9_indice"],
                    f"{br(r['d9_indice'], 2)} · {pct(r.get('pct_do_desperdicio'), 0)} do total") for r in top],
                  330, 150, "Desperdício por categoria (unidades descartadas por casa)")


def desperdicio_por_regiao(rows: list[dict], meta: float | None) -> str:
    ref = (meta, f"meta {br(meta, 0)}%") if meta is not None else None
    return _hbars([(r["regiao"], r["d1_pct"], pct(r["d1_pct"])) for r in rows if r.get("d1_pct") is not None],
                  330, 100, "Taxa de desperdício por região", ref=ref)


def momento_do_descarte(rows: list[dict]) -> str:
    return _hbars([(r["momento"], r["pct"], f"{pct(r['pct'], 0)} ({integer(r['unidades'])})")
                   for r in rows if r.get("pct") is not None], 330, 150, "Momento do descarte", color=SERIES_2)


def categoria_d9(por_categoria: list[dict], limit: int = 8) -> str:
    rows = sorted((c for c in por_categoria if c.get("d9_indice_desperdicio") is not None),
                  key=lambda c: c["d9_indice_desperdicio"], reverse=True)[:limit]
    return _hbars([(c["categoria"], c["d9_indice_desperdicio"], br(c["d9_indice_desperdicio"], 2)) for c in rows],
                  330, 150, "D9: índice de desperdício por categoria")


def categoria_d4(por_categoria: list[dict], meta: float | None, limit: int = 8) -> str:
    rows = sorted((c for c in por_categoria if c.get("d4_pct_a_vencer_7d") is not None),
                  key=lambda c: c["d4_pct_a_vencer_7d"], reverse=True)[:limit]
    ref = (meta, f"alerta {br(meta, 0)}%") if meta is not None else None
    return _hbars([(c["categoria"], c["d4_pct_a_vencer_7d"], pct(c["d4_pct_a_vencer_7d"])) for c in rows],
                  330, 150, "D4: % a vencer em 7 dias por categoria", color=SERIES_2, ref=ref)


def top_abaixo_minimo(items: list[dict]) -> str:
    return _hbars([(a["alimento"], a["households"], integer(a["households"])) for a in items],
                  330, 120, "Alimentos com mais households abaixo do estoque mínimo")


# ---------------------------------------------------------------- UF: vencidos + a vencer (empilhado)
def uf_vencimento(por_uf: list[dict]) -> str:
    """Barra empilhada por UF (vencidos + a vencer em 30 dias), na ordem do ranking D5 (% em risco)."""
    rows = sorted((u for u in por_uf if not u.get("suprimido") and u.get("d5_rank") and u.get("vencidos") is not None
                   and u.get("a_vencer_30d") is not None), key=lambda u: u["d5_rank"])
    if not rows:
        return ""
    width, label_w, row_h, pad_t, gap = 680, 64, 20, 26, 2
    plot_w = width - label_w - 60
    top = _nice_max(max(u["vencidos"] + u["a_vencer_30d"] for u in rows) * 1.05)
    height = pad_t + len(rows) * row_h + 6
    body = (f'<rect x="{label_w}" y="4" width="10" height="10" rx="2" fill="{SERIES_1}"/>'
            + _text(label_w + 14, 13, "Vencidos", 9, INK)
            + f'<rect x="{label_w + 80}" y="4" width="10" height="10" rx="2" fill="{SERIES_2}"/>'
            + _text(label_w + 94, 13, "A vencer em 30 dias", 9, INK))
    for tick in range(5):
        x = label_w + plot_w * tick / 4
        body += (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t - 4}" y2="{pad_t + len(rows) * row_h}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
    for i, u in enumerate(rows):
        y = pad_t + i * row_h + (row_h - BAR_H) / 2
        a, b = u["vencidos"] / top * plot_w, u["a_vencer_30d"] / top * plot_w
        body += _text(label_w - 8, y + BAR_H / 2 + 3.5, f"{u['d5_rank']}º {u['uf']}", 9.5, INK, "end")
        body += f'<rect x="{label_w}" y="{y:.1f}" width="{max(a - gap / 2, 0):.1f}" height="{BAR_H}" fill="{SERIES_1}"/>'
        body += _hbar(label_w + a + gap / 2, y, max(b - gap / 2, 0), BAR_H, SERIES_2)
        total = u["vencidos"] + u["a_vencer_30d"]
        body += _text(label_w + a + b + 6, y + BAR_H / 2 + 3.5, integer(total), 9, INK)
    return _svg(width, height, body, "D5: vencidos e a vencer em 30 dias por UF, na ordem do ranking")


# ---------------------------------------------------------------- D7: distribuição da vida útil
def vida_util_box(vida: dict) -> str:
    """Box plot horizontal da vida útil cadastrada (mín, quartis, mediana, máx)."""
    keys = ("minimo", "p25", "mediana", "p75", "maximo")
    if any(vida.get(k) is None for k in keys):
        return ""
    lo, q1, med, q3, hi = (vida[k] for k in keys)
    width, height, pad = 330, 58, 14
    top = _nice_max(hi)
    plot_w = width - 2 * pad

    def x(v):
        return pad + v / top * plot_w

    cy = 22
    body = (f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{cy}" y2="{cy}" stroke="{INK_2}" stroke-width="1.5"/>'
            f'<line x1="{x(lo):.1f}" x2="{x(lo):.1f}" y1="{cy - 6}" y2="{cy + 6}" stroke="{INK_2}" stroke-width="1.5"/>'
            f'<line x1="{x(hi):.1f}" x2="{x(hi):.1f}" y1="{cy - 6}" y2="{cy + 6}" stroke="{INK_2}" stroke-width="1.5"/>'
            f'<rect x="{x(q1):.1f}" y="{cy - 9}" width="{x(q3) - x(q1):.1f}" height="18" rx="4" fill="{SERIES_1}" '
            f'fill-opacity="0.18" stroke="{SERIES_1}" stroke-width="1.5"/>'
            f'<line x1="{x(med):.1f}" x2="{x(med):.1f}" y1="{cy - 9}" y2="{cy + 9}" stroke="{SERIES_1}" stroke-width="3"/>')
    body += _text(x(med), cy - 13, f"mediana {integer(med)} d", 9, INK, "middle", 600)
    body += _text(x(q1), cy + 22, f"{integer(q1)}", 8.5, INK_2, "middle")
    body += _text(x(q3), cy + 22, f"{integer(q3)}", 8.5, INK_2, "middle")
    body += _text(x(lo), cy + 34, f"mín {integer(lo)}", 8, INK_2, "start")
    body += _text(x(hi), cy + 34, f"máx {integer(hi)}", 8, INK_2, "end")
    return _svg(width, height, body, "D7: distribuição da vida útil cadastrada, em dias")
