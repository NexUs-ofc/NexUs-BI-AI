# NexUs BI · Gerador de relatórios

Serviço separado do chatbot (`app/`) que gera, uma vez por mês, o relatório de **desperdício e validade
nas despensas**: calcula os KPIs, três agentes escrevem a narrativa, e o resultado vira um **JSON no
MongoDB** (que o chatbot lê) e um **PDF** (JSON → HTML → PDF com Playwright) no Google Cloud Storage.

```
dados do mês (mock) ──► análise descritiva (pandas) ──► dados  ──┐
JSONs anteriores (Mongo) ──────────────────────────────────────┤
                         analista ─► insights ─► formalizador ──► narrativa
                                                                  │
                     checagem de números ──► JSON no Mongo (rascunho) ──► chatbot (após publicar)
                                                    └─► HTML (template) ──► PDF ──► GCS
```

**Regra central:** todo número nasce no código (`analysis/descriptive.py`). Os agentes só consultam esses
números por tools e escrevem texto. O status dos KPIs (dentro da meta, alerta…) também é calculado por código.

## Como rodar (PowerShell, na raiz do projeto)

```powershell
pip install -r requirements.txt -r report_generator/requirements-dev.txt
python -m playwright install chromium                         # uma vez por máquina

python -m report_generator.data.mock 2026 10                  # confere o mock
python -m report_generator.run 2026 10 --historico 6 --sem-ia # 6 meses de histórico + outubro, sem Gemini
python -m report_generator.run 2026 10                        # outubro com os agentes (precisa GOOGLE_API_KEY)
python -m report_generator.run 2026 10 --publicar             # gera e já publica (o chatbot passa a ver)
python -m pytest report_generator/tests -q                    # testes (Mongo em memória, sem Gemini)

python -m uvicorn report_generator.api:app --reload --port 8001   # API: http://localhost:8001/docs
python -m report_generator.auth.jwt_handler 1 ADMIN               # token de teste (precisa JWT_SECRET_BASE64)
```

Sem `GCS_BUCKET` no `.env`, o PDF fica em `output/relatorios/AAAA-MM.pdf`. As variáveis estão no
`.env.example` (seção "Gerador de relatórios").

## API (para a interface web)

Todas as rotas pedem `X-API-Key` + `Authorization: Bearer <token do NexUs-Auth>`.
Ler: perfis `REPORT_READ_PROFILES` (padrão COMPANY, ADMIN). Gerar/publicar: `REPORT_WRITE_PROFILES` (padrão ADMIN).
COMPANY só vê relatórios **publicados**.

| Rota | O que faz |
|---|---|
| `POST /reports/{ano}/{mes}/generate?sem_ia=false` | dispara a geração em segundo plano (202) |
| `GET /reports/{ano}/{mes}/status` | `na_fila` → `em_execucao` → `concluido` ou `erro` |
| `GET /reports` | lista os meses (ano, mes, status, gerado_em) |
| `GET /reports/{ano}/{mes}` | JSON do relatório |
| `GET /reports/{ano}/{mes}/html` | prévia em HTML (o mesmo layout do PDF) |
| `GET /reports/{ano}/{mes}/pdf` | o PDF |
| `POST /reports/{ano}/{mes}/publish` | rascunho → publicado |
| `GET /health` | variáveis faltando |

## JSON do relatório

```
{ ano, mes, status: rascunho|publicado, fonte_dados, gerado_em, gerado_com_ia,
  dados: {                       ← números (código). O mês seguinte lê só este bloco como histórico.
    base: { households, itens_na_despensa, eventos_no_mes, data_referencia },
    kpis: { D1, D3, D4, D6, D8: { valor, meta, status, numerador, denominador, mes_anterior, variacao_pp } },
    vida_util (D7), por_uf (D3, D5), por_categoria (D4, D7, D9), top_abaixo_minimo (D6) },
  narrativa: { resumo_executivo, analise_por_kpi[], insights[], recomendacoes[], limitacoes[] },  ← agentes
  qualidade: { numeros_sem_fonte[], meses_de_historico },
  pdf: { uri } }
```

O contrato fica em `schemas.py`; KPIs, fórmulas e metas em `kpis.py` (único lugar para mudar uma meta).

## Tickets

| Ticket | Onde |
|---|---|
| NI-404 Pipeline de análise descritiva manual | `analysis/descriptive.py`, `pipeline.py` |
| NI-405 Template de relatório | `rendering/templates/relatorio.html`, `rendering/html.py` |
| NI-406 Serviço de PDFs em bucket | `storage/files.py` (GCS; pasta local em dev) |
| NI-407 Collection de FAQs no Qdrant | descartado |
| NI-408 Agente analista primário | `agents/prompts/analyst.py`, `agents/narrative.py` |
| NI-409 Leitura dos JSONs anteriores no Mongo | `storage/mongo.py`, `tools/history_tools.py` |
| NI-410 Tools de análise descritiva | `tools/analysis_tools.py` |
| NI-411 Tools de cálculo | `tools/calc_tools.py` |
| NI-412 Agente gerador de insights | `agents/prompts/insights.py` |
| NI-413 Agente formalizador do JSON | `agents/prompts/formalizer.py` (saída estruturada = `Narrativa`) |
| NI-414 Agentes gerais | `agents/base.py` |
| NI-415 Gráficos | fora do relatório (ficam no dashboard); o dashboard pode ler o bloco `dados` |
| NI-416 Gerador de PDF | `rendering/pdf.py` (Playwright / Chromium) |
| NI-417 Autenticação | `auth/` (copiado do NexUs-AI / `app/auth`) |

## Premissas do MVP (a validar com o time)

- **"qtd" em D3, D4 e D8 = nº de itens** (linhas de `pantry_item`), não a soma de `quantity`.
- **D1 conta eventos** do mês (`records`), não soma `discarded_quantity`.
- **Data de referência = último dia do mês.** D4 conta o que vence de 0 a 7 dias depois dela; vencidos ficam no D3.
- **D6:** só households com mínimo > 0; "abaixo" = ao menos um alimento com total na despensa menor que o mínimo.
- **D9** é um índice (expirados por household), não porcentagem.
- **Privacidade:** UF com menos de `REPORT_MIN_HOUSEHOLDS` (10) households não mostra números.
- **Dados mockados:** `data/mock.py` gera, por mês, as mesmas colunas das tabelas do NexUs-db.

## Para sair do mock

`pantry_item` guarda só o estado atual da despensa, então não dá para saber como ela estava no fim de um
mês passado. Para a base real é preciso uma **foto mensal da despensa** (tabela de snapshot ou view de BI
no NexUs-db). Com isso, basta implementar `_load_from_db` em `data/loader.py` devolvendo os mesmos
DataFrames e usar `REPORT_DATA_SOURCE=db`. Nada mais no pipeline muda.
