"""Séries para gráficos no site (JSON simples, sem HTML/SVG), montadas a partir do relatório já salvo.

O site pode chamar `GET /reports/{ano}/{mes}/charts` e desenhar com a biblioteca que preferir. Tudo vem do
documento do Mongo: nenhuma consulta ao Databricks (a Free Edition tem cota).

Cada bloco é uma lista de objetos com chaves estáveis. `disponivel.despensa=false` avisa o front para
esconder a visão Despensa (mês sem foto da despensa).
"""
from report_generator.kpis import KPIS


def _kpi(k: dict) -> dict:
    return {"codigo": k["codigo"], "nome": k["nome"], "valor": k["valor"], "unidade": k["unidade"],
            "meta": k.get("meta"), "status": k["status"], "variacaoPp": k.get("variacao_pp"),
            "mesAnterior": k.get("mes_anterior")}


def charts_payload(report: dict) -> dict:
    d = report["dados"]
    tem_despensa = d.get("tem_despensa", True)
    kpis = d.get("kpis", {})
    evento = [_kpi(kpis[c]) for c in ("D1", "D2") if c in kpis and kpis[c]["valor"] is not None]
    estado = [_kpi(kpis[c]) for c in ("D3", "D4", "D6", "D8") if tem_despensa and c in kpis
              and kpis[c]["valor"] is not None]
    resumo = d.get("resumo") or {}
    vida = d.get("vida_util") or {}
    return {
        "periodo": {"ano": report["ano"], "mes": report["mes"], "parcial": bool(d.get("parcial")),
                    "status": report.get("status"), "geradoEm": report.get("gerado_em"),
                    "dataFotoDespensa": d.get("data_foto_despensa")},
        "disponivel": {"despensa": tem_despensa, "uf": bool(d.get("por_uf")),
                       "evolucao": len(d.get("evolucao") or []) > 1},
        "resumo": {"unidadesSaidas": resumo.get("unidades_saidas"),
                   "unidadesDescartadas": resumo.get("unidades_descartadas"),
                   "casasComMovimento": resumo.get("casas_com_movimento"),
                   "avaliados": resumo.get("avaliados"), "foraDaMeta": resumo.get("fora_da_meta")},
        "kpis": {"desperdicio": evento, "despensa": estado},
        "evolucao": [{"anoMes": p["ano_mes"], "taxaDesperdicio": p.get("d1"), "descarteEsquecimento": p.get("d2"),
                      "completo": p.get("completo", True)} for p in d.get("evolucao", [])],
        "metas": {"taxaDesperdicio": KPIS["D1"].meta},
        "categorias": [{"categoria": c["categoria"], "unidadesDescartadas": c["unidades_descartadas"],
                        "unidadesSaidas": c["unidades_saidas"], "casas": c["casas"], "taxaDesperdicio": c.get("d1_pct"),
                        "desperdicioPorCasa": c.get("d9_indice"), "participacaoPct": c.get("pct_do_desperdicio")}
                       for c in d.get("desperdicio_categoria", [])],
        "regioes": [{"regiao": r["regiao"], "unidadesDescartadas": r["unidades_descartadas"],
                     "unidadesSaidas": r["unidades_saidas"], "taxaDesperdicio": r.get("d1_pct"),
                     "descarteEsquecimento": r.get("d2_pct")} for r in d.get("desperdicio_regiao", [])],
        "momentoDescarte": [{"momento": m["momento"], "unidades": m["unidades"], "pct": m.get("pct")}
                            for m in d.get("momento_descarte", [])],
        "despensa": None if not tem_despensa else {
            "porUf": [{"uf": u["uf"], "suprimido": u.get("suprimido", False), "vencidos": u.get("vencidos"),
                       "aVencer30d": u.get("a_vencer_30d"), "pctEmRisco": u.get("d5_pct_em_risco"),
                       "pctVencidos": u.get("d3_pct_vencidos"), "ranking": u.get("d5_rank")}
                      for u in d.get("por_uf", [])],
            "porCategoria": [{"categoria": c["categoria"], "pctAVencer7d": c.get("d4_pct_a_vencer_7d"),
                              "medianaValidadeDias": c.get("d7_mediana_dias")}
                             for c in d.get("por_categoria", []) if c.get("d4_pct_a_vencer_7d") is not None],
            "abaixoDoMinimo": [{"alimento": a["alimento"], "categoria": a["categoria"], "casas": a["households"]}
                               for a in d.get("top_abaixo_minimo", [])],
            "validade": {"mediana": vida.get("mediana"), "p25": vida.get("p25"), "p75": vida.get("p75"),
                         "minimo": vida.get("minimo"), "maximo": vida.get("maximo")},
        },
        "acoesApp": report.get("acoes_app", []),
        "kpiNomes": {code: k.nome for code, k in KPIS.items()},
    }
