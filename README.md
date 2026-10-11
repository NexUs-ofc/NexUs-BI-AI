# NexUs BI AI

Assistente multiagente de Business Intelligence (API FastAPI). A empresa pergunta em português e o
sistema responde sobre o NexUs BI ou sobre os relatórios mensais, com um juiz conferindo cada resposta.

**Stack:** Python · FastAPI · LangChain 1.x (`create_agent`) · LangGraph · Gemini · Qdrant · MongoDB · PostgreSQL · LangSmith

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env                    # preencha as variáveis (veja o próprio arquivo)
python -m app.model.llm                 # 1. a chave do Gemini funciona?
python -m app.services.faq_service      # 2. carrega o FAQ no Qdrant
python -m app.auth.jwt_handler <id>     # 3. gera um token de teste
python -m uvicorn app.app:app --reload  # 4. sobe a API: http://localhost:8000/docs
```

## Comandos do projeto

Rode na raiz do projeto.

| Para quê | Comando |
|---|---|
| Instalar as dependências | `pip install -r requirements.txt` |
| Subir a API (docs em http://localhost:8000/docs) | `python -m uvicorn app.app:app --reload` |
| Carregar o `faq.json` no Qdrant (sempre que editar o FAQ) | `python -m app.services.faq_service` |
| Testar a chave do Gemini | `python -m app.model.llm` |
| Gerar um token de teste para uma empresa (vale 8h) | `python -m app.auth.jwt_handler <profile_id>` |
| Desenhar o grafo em Mermaid (cole em mermaid.live) | `python -m app.core.orchestrator` |

## Verificações

Comandos de diagnóstico para conferir se cada parte está funcionando (PowerShell, na raiz do projeto).

| O que confere | Comando | Resultado esperado |
|---|---|---|
| FAQ carregado no Qdrant | `python -c "from app.repository.faq_repository import get_qdrant; from app.config import QDRANT_COLLECTION_FAQ as c; q = get_qdrant(); e = q.collection_exists(c); print('coleção:', c, '- existe:', e, '- itens:', q.count(c).count if e else 0)"` | `existe: True` e o nº de itens do `faq.json` |
| Empresas ativas no Postgres do Auth (ids para o token) | `python -c "import psycopg; from app.config import PGSQL_URL; c = psycopg.connect(PGSQL_URL); print(c.execute('select p.id, p.name from company c join profile p on p.id = c.profile_id where p.type = %s and p.status = %s', ('COMPANY', 'ACTIVE')).fetchall())"` | lista de `(id, nome)` |
| Consulta de empresa da API | `python -c "from app.repository.company_repository import find_active_company_id as f; print(f(999999))"` | `None` (troque por um id ativo para ver o id da empresa) |
| Chave e workspace do LangSmith | `python -c "import app.config; from langsmith import Client; print([p.name for p in Client().list_projects(name_contains='ceris')])"` | lista com os projetos `ceris-ms-ia...` |
| Métricas sendo gravadas (últimas 24h) | `python -c "from app.repository.metrics_repository import find_metrics_since as f; from datetime import datetime, timedelta, timezone; d = f(datetime.now(timezone.utc) - timedelta(days=1)); print(len(d), 'métricas'); print(d[-1] if d else '')"` | 1 ou mais métricas depois de fazer perguntas |
| Cotação do dólar usada no relatório | `python -c "from app.observability.cost import get_usd_to_brl; print(get_usd_to_brl())"` | `(valor, 'PTAX Banco Central dd/mm/aaaa')` |
| Gerar uma chave aleatória (ex.: nova `API_KEY`) | `python -c "import secrets; print(secrets.token_hex(32))"` | texto de 64 caracteres |

## Como chamar a API

As rotas `/chat` exigem dois headers (mesmo esquema do NexUs-AI):

| Header | O que é |
|---|---|
| `X-API-Key` | chave da aplicação (`API_KEY` do `.env`) |
| `Authorization: Bearer <token>` | token do login no site, emitido pelo NexUs-Auth |

O token precisa ser de um perfil **COMPANY** com empresa **ACTIVE** no PostgreSQL do Auth; outros perfis
recebem 403. Para testar sem o site, gere um token com `python -m app.auth.jwt_handler <profile_id>`.

| Rota | O que faz |
|---|---|
| `POST /chat` | `{"question", "session_id"?, "debug"?}` → `{"session_id", "answer", "route", "steps"}` |
| `DELETE /chat/{session_id}` | apaga a memória da sessão |
| `GET /metrics/report` | custo, latência, erros e ROI (só `X-API-Key`) |
| `GET /health` | status e variáveis faltando (sem autenticação) |

Para continuar uma conversa, reenvie o `session_id`. Com `"debug": true` a resposta mostra o passo a passo.

## Como funciona

O orquestrador é um **grafo do LangGraph**: cada etapa é um nó e as decisões são arestas.

```
input_guardrail ──bloqueado──> fim
       │
     router ──fora de escopo──> finish
       │
   specialist <───┐ reprovado (refaz 1x)
       │          │
     judge ───────┘
       │ aprovado
     finish (guardrail de saída + memória) ──> fim
```

| Agente | Papel | Ferramentas |
|---|---|---|
| Guardrails | bloqueiam injeção de prompt, perguntas sobre o sistema e pedidos ilegais; mascaram CPF, e-mail etc. | regras fixas (sem LLM) |
| Roteador | escolhe `faq`, `analyst`, `recommender` ou `out_of_scope` | saída estruturada |
| FAQ | dúvidas sobre o NexUs BI e conceitos de BI | `search_faq` (Qdrant) |
| Analista | descreve os números dos relatórios | `search_reports_by_period`, `get_latest_reports` |
| Recomendador | insights e **previsão** de tendência; nunca decide | mesmas do analista |
| Juiz | reprova alucinação, desvio de papel e partes ignoradas | checagem automática de números + `search_context` |

Os prompts ficam em `app/core/prompts/`, um arquivo por agente, com regras e exemplos (few-shot).

**Princípio da inferência:** cada agente recebe **dados novos** (pergunta, relatórios, FAQ) e aplica o
**conhecimento aprendido** (o modelo pré-treinado + regras e exemplos do prompt) para gerar uma **resposta**
(FAQ, analista), uma **previsão** (recomendador) ou uma **decisão** (roteador, juiz).

## Dados

| Fonte | Uso |
|---|---|
| Qdrant | FAQ (`app/static/faq.json`); rode o `faq_service` sempre que editar o JSON |
| MongoDB `db_ceris` | relatórios mensais (um por mês, igual para todas as empresas; campos obrigatórios `mes` e `ano`) e métricas |
| PostgreSQL do Auth | confere se a empresa do token existe e está ativa |
| Memória | só em RAM, por empresa + sessão; reiniciar o servidor apaga |

## Observabilidade

- **LangSmith:** com `LANGSMITH_TRACING=true`, cada pergunta vira uma árvore no projeto `ceris-ms-ia-bi`
  (orquestrador → nós do grafo com `@traceable` → agentes, Gemini e tools).
- **MongoDB:** coleções próprias do web, separadas das do mobile e ligadas pelo `trace_id`:
  `metrics_bi` (uma por pergunta) e `tool_metrics_bi` (uma por chamada de tool).
- **`GET /metrics/report`:** custo para 100 e 1000 usuários/semana, latência de cada agente e total, índice de
  erros, custo por resolução e ROI. O dólar vem da PTAX do Banco Central. As premissas mudam pela URL, ex.:
  `/metrics/report?days=30&analyst_hour_brl=80`.

## Estrutura

```
app/
  app.py, config.py   API e variáveis do .env
  controller/         rotas (só chamam os services)
  services/           chat, FAQ (ingestão) e relatório de métricas
  core/               agentes, grafo do orquestrador e memória
  core/prompts/       prompts e descrições das tools
  tools/              tools dos agentes (relatórios, FAQ, juiz)
  guardrails/         regras de entrada e saída
  auth/               X-API-Key e JWT
  repository/         Qdrant, MongoDB e PostgreSQL
  observability/      custo e métricas
  model/              LLM e embeddings (Gemini)
  schemas/            contratos da API e entre agentes
```
