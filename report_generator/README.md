# NexUs BI · Gerador de relatórios

Serviço separado do chatbot (`app/`) que gera, uma vez por mês, o relatório de **desperdício e validade
nas despensas**: lê os KPIs oficiais do mês na camada **Gold do Databricks**, os agentes escrevem a
narrativa (analista e cientista de dados **em paralelo**, depois o formalizador), e o resultado vira um
**JSON no MongoDB** (que o chatbot lê) e um **PDF** com gráficos (JSON → HTML → PDF com Playwright) no
Supabase Storage. A mesma API entrega ao site os dados do **Dashboard** e a lista de PDFs por mês.

```
KPIs do mês: Gold do Databricks (prontos) ou mock (pandas) ──────────► dados ──┐
JSONs anteriores (Mongo) ───────────────────────────────────────────────────┤
                         ┌─ analista descritivo ─┐  (asyncio, ao mesmo tempo)
                         └─ cientista de dados ──┴─► formalizador ──► narrativa
                                                                  │
                     checagem de números ──► JSON no Mongo (já publicado) ──► site e chatbot
                                                    └─► HTML (template + gráficos) ──► PDF ──► Supabase Storage
```

**Regra central:** todo número nasce no código (`analysis/descriptive.py`). Os agentes só consultam esses
números por tools e escrevem texto. O status dos KPIs (dentro da meta, alerta…) também é calculado por código.

## Como rodar (PowerShell, na raiz do projeto)

```powershell
pip install -r requirements.txt -r report_generator/requirements-dev.txt
python -m playwright install chromium                         # uma vez por máquina

python -m report_generator.data.mock 2026 10                  # confere o mock
python -m report_generator.run --mes-anterior                 # o mês que acabou (IA + JSON + PDF); não refaz se já existe
python -m report_generator.run 2026 10                        # gera um mês específico
python -m report_generator.run 2026 10                 # gera (já fica publicado: o site e o chatbot veem)
python -m report_generator.run 2026 9 --historico 6 --atualizar-pdfs  # cria histórico que falta e refaz os PDFs
python -m report_generator.run --atualizar-pdfs               # refaz os PDFs de todos os relatórios (sem IA)
python -m pytest report_generator/tests -q                    # testes (Mongo em memória, sem Gemini)

python -m uvicorn app.app:app --reload   # API única (chatbot + relatórios): http://localhost:8000/docs
python -m report_generator.auth.jwt_handler 1 ADMIN               # token de teste (precisa JWT_SECRET_BASE64)
```

Sem `SUPABASE_URL` no `.env`, o PDF fica em `output/relatorios/AAAA-MM.pdf`. As variáveis estão no
`.env.example` (seção "Gerador de relatórios").

### Geração automática (todo mês)

Com a API rodando (`uvicorn`), o `scheduler.py` gera sozinho o relatório do mês anterior todo dia
`REPORT_SCHEDULE_DAY` às `REPORT_SCHEDULE_HOUR` (padrão: dia 1, 03:00 de Brasília), com IA e PDF no Supabase.
Se a API estava desligada no horário, gera assim que subir. Se o relatório do mês já existe, não refaz.
Todo relatório já sai publicado: não há etapa de rascunho nem endpoint de publicar.
Hospedagem que desliga a API ociosa (Cloud Run): agende `python -m report_generator.run --mes-anterior`
num cron externo (mesma regra: não refaz o mês se ele já existe; `--forcar` refaz).

O PDF usa o Chromium do Playwright; sem ele, usa o Edge ou o Chrome da máquina (`REPORT_PDF_BROWSER`).

### PDFs no Supabase Storage

1. No painel do Supabase, crie um bucket **privado** (ex.: `relatorio`) em Storage.
2. Preencha no `.env`: `SUPABASE_URL` (https://<projeto>.supabase.co), `SUPABASE_SERVICE_ROLE_KEY`
   (Project Settings → API) e `SUPABASE_BUCKET`.
3. Cada PDF vai para `{SUPABASE_PREFIX}/{ano}/{mes}.pdf` (gerar de novo o mês sobrescreve) e o Mongo guarda
   a URI `supabase://<bucket>/<caminho>`. O site lista os PDFs por mês em `GET /reports` e abre/baixa pelo
   `GET /reports/{ano}/{mes}/pdf`, que confere o perfil do usuário; a service role key nunca vai para o front-end.

### Gráficos do relatório

Ficam em `rendering/charts.py`: SVG gerado em Python a partir do bloco `dados` (sem JavaScript nem CDN,
então a prévia HTML e o PDF saem iguais e o PDF não depende de rede). O relatório traz:
barra de cada KPI contra a meta (nos cards), evolução mensal dos KPIs (usa os meses anteriores do Mongo),
vencidos e a vencer por UF (ranking D5), D9 e D4 por categoria, distribuição da vida útil (D7) e alimentos
abaixo do estoque mínimo (D6). As tabelas continuam no relatório com os números exatos.

## API (para a interface web)

Todas as rotas pedem `X-API-Key` + `Authorization: Bearer <token do NexUs-Auth>`.
Ler: perfis `REPORT_READ_PROFILES` (padrão COMPANY, ADMIN). Gerar: `REPORT_WRITE_PROFILES` (padrão ADMIN).


| Rota | Quem | O que faz |
|---|---|---|
| `GET /dashboard?ano=&mes=` | leitura | dados de todas as visualizações do Dashboard (padrão: último mês fechado), no formato `DashboardData` do NexUs-Web |
| `GET /reports?meses=6&busca=` | leitura | PDFs agrupados por mês, do mais recente para o mais antigo (tela Relatórios) |
| `GET /reports/{ano}/{mes}` | leitura | JSON do relatório |
| `GET /reports/{ano}/{mes}/pdf` | leitura | o PDF; `?download=true` baixa em vez de abrir |
| `POST /reports/{ano}/{mes}/generate` | escrita | dispara a geração em segundo plano (202) |
| `GET /reports/{ano}/{mes}/status` | escrita | `na_fila` → `em_execucao` → `concluido` ou `erro` |
| `GET /health` | — | variáveis faltando |

Exemplo de `GET /reports`:

```json
{"total": 2, "meses": [
  {"id": "2026-10", "ano": 2026, "mes": 10, "titulo": "Outubro 2026", "total": 1, "relatorios": [
    {"id": "2026-10", "titulo": "Desperdício e validade nas despensas", "data": "2026-10-31", "tipo": "Mensal",
     "status": "publicado", "geradoComIa": true, "geradoEm": "2026-11-01T06:02:11Z",
     "pdf": "/reports/2026/10/pdf", "download": "/reports/2026/10/pdf?download=true"}]},
  {"id": "2026-09", "...": "..."}]}
```

### Dashboard

`analysis/gold.py` (Gold) ou `analysis/dashboard.py` (mock) monta o JSON a partir dos mesmos números do relatório, mais os recortes que só a
tela usa (região, heatmap categoria × região, histograma e boxplot de vida útil). O formato é exatamente o
`DashboardData` do front (`src/types/dashboard.ts`), então no NexUs-Web basta trocar o mock em
`dashboard.service.ts` por uma chamada a `GET /dashboard`. Observações:

- A base não guarda peso: os campos `...Kg`, `volume` e `kilograms` levam **contagem de unidades/itens**
  (`meta.unidade`). Ajuste o rótulo "kg" no front.
- Com a Gold, os gráficos que ela ainda não cobre vêm vazios e são listados em `meta.semDadosNaGold`.
- UFs e regiões abaixo do mínimo de privacidade são omitidas (o front não aceita `null`).
- O resultado de cada mês fica em memória por `REPORT_DASHBOARD_CACHE_SECONDS` (padrão 15 min).

## JSON do relatório

```
{ ano, mes, status: publicado, fonte_dados, gerado_em, gerado_com_ia,
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
| NI-406 Serviço de PDFs em bucket | `storage/files.py` (Supabase Storage; pasta local em dev) |
| NI-407 Collection de FAQs no Qdrant | descartado |
| NI-408 Agente analista primário | `agents/prompts/analyst.py`, `agents/narrative.py` |
| NI-409 Leitura dos JSONs anteriores no Mongo | `storage/mongo.py`, `tools/history_tools.py` |
| NI-410 Tools de análise descritiva | `tools/analysis_tools.py` |
| NI-411 Tools de cálculo | `tools/calc_tools.py` |
| NI-412 Agente cientista de dados (insights) | `agents/prompts/data_scientist.py`; roda em paralelo com o analista |
| NI-413 Agente formalizador do JSON | `agents/prompts/formalizer.py` (saída estruturada = `Narrativa`) |
| NI-414 Agentes gerais | `agents/base.py` |
| NI-415 Gráficos | `rendering/charts.py` (SVG no relatório); `analysis/dashboard.py` + `GET /dashboard` (site) |
| NI-416 Gerador de PDF | `rendering/pdf.py` (Playwright / Chromium) |
| NI-417 Autenticação | `auth/` (copiado do NexUs-AI / `app/auth`) |

## Premissas do MVP (a validar com o time)

- **"qtd" em D3, D4 e D8 = nº de itens** (linhas de `pantry_item`), não a soma de `quantity`.
- **D1 conta eventos** do mês (`records`), não soma `discarded_quantity`.
- **Data de referência = último dia do mês.** D4 conta o que vence de 0 a 7 dias depois dela; vencidos ficam no D3.
- **D6:** só households com mínimo > 0; "abaixo" = ao menos um alimento com total na despensa menor que o mínimo.
- **D9** é um índice (expirados por household), não porcentagem.
- **Privacidade:** UF com menos de `REPORT_MIN_HOUSEHOLDS` (10) households não mostra números.
- **Dados mockados:** `data/mock.py` gera, por mês, as mesmas colunas das tabelas do NexUs-db
  (`REPORT_DATA_SOURCE=mock`, padrão em desenvolvimento).

## Dados do Databricks (camada Gold)

Com `REPORT_DATA_SOURCE=databricks`, os números vêm das tabelas `kpi_*` de `workspace.gold`, atualizadas
todo dia às 07:00 pelo `Job_NexUs_BI` (`data/databricks.py` lê; `analysis/gold.py` converte). São os KPIs
**oficiais**: o catálogo `kpis.py` usa as mesmas metas (D1 ≤ 15, D3 ≤ 5, D4 ≤ 10, D6 ≤ 30, D8 ≤ 10) e a mesma
definição de D5 (% das unidades em risco). "Unidades" são embalagens; a base não tem peso nem R$.

| Tabela | Usada para |
|---|---|
| `kpi_desperdicio_mensal` | D1 e D2 do mês e a série mensal do gráfico (relatório e Dashboard) |
| `kpi_estado_diario` | D3, D4, D6, D7 e D8 pela última foto da despensa do mês |
| `kpi_uf` | ranking D5 e mapa por UF (UF com menos de `REPORT_MIN_LOTES_UF` = 30 lotes fica de fora) |
| `kpi_categoria` | D9, vida útil e participação de cada categoria no desperdício (sem "Não informada") |
| `kpi_cards` | data da foto |

Os recortes que as `kpi_*` não têm saem de consultas agregadas sobre `fato_*` + `dim_*` (nunca o fato inteiro
pela rede, só os totais):

| Tabela (consulta) | Fato + dim usados | Usada para |
|---|---|---|
| `estoque_total` | `fato_estoque` + `dim_alimento` | households, quartis/outliers de vida útil (relatório) |
| `estoque_categoria` | `fato_estoque` + `dim_alimento` | D4 e quartis de vida útil por categoria (relatório/boxplot) |
| `vida_util_faixas` | `fato_estoque` + `dim_alimento` | histograma de vida útil (Dashboard) |
| `regiao_categoria` | `fato_movimento` + `dim_alimento` + `dim_localidade` | desperdício/consumo por categoria × região (Dashboard) |
| `abaixo_minimo` | `fato_estoque_minimo` + `dim_alimento` | top 10 alimentos abaixo do mínimo (relatório/Dashboard) |

Todas usam a última foto do mês pedido (`fato_estoque`/`fato_estoque_minimo`) ou o mês inteiro
(`fato_movimento`), e devolvem só os totais já agrupados (dezenas de linhas, nunca o fato inteiro).

Configurar no `.env`:

- `DATABRICKS_SERVER_HOSTNAME` e `DATABRICKS_HTTP_PATH`: no workspace do Databricks, **SQL Warehouses** →
  o warehouse (Serverless Starter Warehouse) → aba **Connection details** → copie "Server hostname" e
  "HTTP path".
- `DATABRICKS_TOKEN`: **User Settings** (ícone do seu usuário) → **Developer** → **Access tokens** →
  "Generate new token". Copie o valor na hora — ele some depois do "Generate".
- `DATABRICKS_CATALOG` e `DATABRICKS_SCHEMA`: os valores já usados na consulta que você rodou em
  `information_schema.columns` — pelo resultado mostrado, `workspace` e `gold` (os defaults deste projeto).

O warehouse da Free Edition demora alguns segundos para acordar e tem cota diária: o `GET /dashboard`
guarda cada mês em memória por `REPORT_DASHBOARD_CACHE_SECONDS` (1 hora) e o relatório consulta uma vez
por mês.

Observações: UF e categoria são a foto do dia em que roda (o relatório do mês fechado roda no dia 1, então
reflete o fim do mês); o histórico de estado começa em 25/10/2026; percentuais são arredondados para 1 casa;
vencidos e a vencer por UF são derivados dos percentuais oficiais. `REPORT_DATA_SOURCE=mock` continua
disponível para desenvolvimento e testes, sem warehouse.


## Versão 2 do relatório (3 visões, mês a mês)

O PDF/JSON agora tem **Visão geral · Desperdício · Despensa**, sem os códigos D1/D2 (o leitor vê só os nomes).

- **Indicadores de evento** (taxa de desperdício, descarte por esquecimento, desperdício por categoria, por
  região e momento do descarte) são filtrados pelo mês via `fato_movimento.ano_mes_evento` e existem em qualquer
  mês com movimento. **Desperdício por categoria** = unidades descartadas da categoria no mês ÷ casas que
  movimentaram a categoria no mês.
- **Indicadores de estado** (vencidos, a vencer, sem validade, abaixo do mínimo, prazo de validade, risco por
  estado) dependem da foto da despensa. Mês sem foto = `dados.tem_despensa=false`: a visão Despensa, os cards e
  as ações de estado somem do PDF, e as consultas de estado nem vão ao Databricks.
- Topo: unidades que saíram, unidades descartadas, casas com movimento e "X de Y avaliados fora da meta".
- Evolução dos últimos 6 meses (taxa de desperdício e descarte por esquecimento) vem de `kpi_desperdicio_mensal`.
- `acoes_app`: recomendações concretas para o app (alerta pós-vencimento, lembrete para as categorias líderes,
  cadastro de validade...), geradas por regras em `analysis/acoes.py` e ligadas aos números do mês.

### Agendamento diário (teste)

`REPORT_SCHEDULE_FREQUENCY=diario` (padrão): todo dia às `REPORT_SCHEDULE_HOUR` (use 8, depois da Gold das 7h)
gera o **mês atual parcial** (sobrescreve o do dia anterior, mantém "publicado" e o PDF) e, quando o mês vira,
fecha o anterior uma vez. Cron externo: `python -m report_generator.run --diario`. Para voltar ao modelo mensal:
`REPORT_SCHEDULE_FREQUENCY=mensal`.

### Coleções do MongoDB

Só duas são do gerador: `reports` (o JSON, 1 por mês) e `report_jobs` (andamento, 1 por mês, com as últimas 20
execuções em `historico`). O chatbot usa também `metrics_bi` e `tool_metrics_bi`; o Qdrant usa `faq`.
Qualquer outra (ex.: `reports_mock`) não é usada pelo código. `python -m report_generator.diagnostico` lista tudo,
mostra o `erro` do último job e testa Mongo, Supabase e Databricks (`--escrever` testa gravação).

### Endpoints para o site

| Rota | O que devolve |
|---|---|
| `GET /reports/{ano}/{mes}/charts` | séries prontas para gráficos (resumo, evolução, categorias, regiões, momento, UF, ações do app); lido do Mongo, sem consultar o Databricks |
| `GET /reports/{ano}/{mes}/pdf-url` | URL assinada e temporária do PDF no bucket privado do Supabase (o front abre direto, sem a service key) |
| `GET /reports/{ano}/{mes}/pdf` | o PDF pela API (o site usa como alternativa quando não há Supabase e para o botão Baixar) |

Supabase: chaves novas `sb_secret_...` vão só no header `apikey` (o código já faz isso); chaves JWT antigas usam os dois.
