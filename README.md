# NexUs BI AI

Assistente de Business Intelligence (API FastAPI). A empresa pergunta em português e o sistema responde
sobre o NexUs BI (FAQ no Qdrant) ou sobre os relatórios mensais (MongoDB), conferindo cada número da
resposta contra os dados consultados.

**Stack:** Python · FastAPI · LangChain 1.x (`create_agent`) · Gemini (Interactions API) · Qdrant · MongoDB · PostgreSQL · LangSmith

O projeto tem duas partes:

| Parte | Pasta | O que faz |
|---|---|---|
| Chatbot | `app/` | responde perguntas sobre o NexUs BI e sobre os relatórios mensais |
| Gerador de relatórios | `report_generator/` | gera o relatório do mês (JSON no MongoDB + PDF). Veja [report_generator/README.md](report_generator/README.md) |

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
| Gerar uma chave aleatória (ex.: nova `API_KEY` ou `ADMIN_API_KEY`) | `python -c "import secrets; print(secrets.token_hex(32))"` | texto de 64 caracteres |

## Como chamar a API

As rotas `/chat` exigem dois headers (mesmo esquema do NexUs-AI):

| Header | O que é |
|---|---|
| `X-API-Key` | chave da aplicação (`API_KEY` do `.env`) |
| `Authorization: Bearer <token>` | token do login no site, emitido pelo NexUs-Auth |

O token precisa ser de um perfil de `CHAT_PROFILES` (padrão `COMPANY,ADMIN`, os mesmos que leem os
relatórios). COMPANY precisa ter empresa **ACTIVE** no PostgreSQL do Auth; HOUSEHOLD e STORE recebem 403.
Para testar sem o site: `python -m app.auth.jwt_handler <profile_id> [COMPANY|ADMIN]`.

Erros do `POST /chat` (o campo `detail` diz o motivo e o front mostra como veio):

| Status | Quando |
|---|---|
| 503 | MongoDB, Qdrant ou PostgreSQL fora do ar ou mal configurado (ex.: FAQ não indexado). Nunca responde com dado inventado |
| 502 | a chamada ao Gemini falhou (cota, chave, modelo, rede) |
| 504 | a pergunta passou de `CHAT_TIMEOUT_S` |

| Rota | O que faz |
|---|---|
| `POST /chat` | `{"question", "session_id"?, "debug"?}` → `{"session_id", "answer", "route", "steps"}` |
| `DELETE /chat/{session_id}` | apaga a memória da sessão |
| `GET /health` | status e variáveis faltando (sem autenticação) |

As rotas do painel do administrador usam outra chave, no header `X-Admin-Key` (`ADMIN_API_KEY` do `.env`).
É a mesma em todos os serviços do NexUs, para o painel entrar uma vez só; a `API_KEY` das empresas não abre
estas rotas. O contrato completo está em [Painel do administrador](docs/painel-admin.md).

| Rota | O que faz |
|---|---|
| `GET /admin/session` | confirma a chave no login do painel |
| `GET /admin/metrics?dias=7` | a página do BI IA no painel: resumo, desempenho, custo e qualidade (MongoDB) |
| `GET /admin/report?dias=7` | o período contra o período anterior de mesmo tamanho |
| `GET /admin/langsmith?dias=7` | execuções por dia, p50/p99 por chain e por agente, feedback (LangSmith) |
| `GET /admin/roi` | custo, cenários para 100 e 1000 usuários e ROI em reais (era `GET /metrics/report`) |

Para continuar uma conversa, reenvie o `session_id`. Com `"debug": true` a resposta mostra o passo a passo.

## Como funciona

O orquestrador (`app/core/orchestrator.py`) é Python puro, sem grafo:

```
guardrail de entrada (regras, sem LLM) ──bloqueado──> responde o motivo
       │
   assistente: 1 agente (Gemini) com as tools search_faq, search_reports_by_period, get_latest_reports
       │                     ▲
 conferência de números ─────┘ número fora dos dados -> refaz 1x (MAX_JUDGE_RETRIES), depois desiste
 (código, sem LLM)
       │ ok
 guardrail de saída + memória da sessão ──> resposta
```

| Etapa | O que faz | Chamadas ao Gemini |
|---|---|---|
| Guardrails | bloqueiam injeção de prompt, perguntas sobre o sistema e pedidos ilegais; mascaram CPF, e-mail etc. | 0 |
| Assistente | decide se precisa do FAQ (Qdrant) ou dos relatórios (MongoDB), consulta e responde. Descreve números, aponta percepções/tendências e nunca decide | 1 sem tool (saudação, conceito de BI); 2 com uma tool |
| Conferência de números | todo número relevante da resposta precisa estar nos dados consultados (aceita arredondamento e a conta mostrada: soma/diferença de dois dados) | 0 |

A rota devolvida (`route`) vem das tools usadas: `analyst` leu relatórios, `faq` consultou o FAQ ou não
precisou de dados. O prompt fica em `app/core/prompts/assistant.py`.

Antes eram roteador + 3 especialistas + juiz por LLM: de 4 a 12 chamadas ao Gemini em série por pergunta.
Escolher a fonte é o que o tool calling já faz, e a checagem de números do juiz já era código.

**Gemini 3.x:** o wrapper `ChatGoogleInteractions` (`app/model/llm.py`) devolve ao modelo os passos
`thought` (com a assinatura) de cada chamada de tool, não envia `temperature` (o Gemini 3 não aceita) e usa
`LLM_THINKING_LEVEL` (padrão `low`, o indicado para chat em tempo real). O SDK repete sozinho chamadas com
erro 408/409/429/5xx: `LLM_MAX_RETRIES` limita isso (sem configurar seriam até 4 requisições por chamada).

## Dados

| Fonte | Uso |
|---|---|
| Qdrant | FAQ (`app/static/faq.json`); rode o `faq_service` sempre que editar o JSON |
| MongoDB `db_ceris` | relatórios mensais gerados pelo `report_generator` (um por mês, igual para todas as empresas; o chatbot só lê os publicados) e métricas |
| PostgreSQL compartilhado | confere se a empresa do token existe e está ativa e consulta os nomes em `public.food` para os rankings |
| Redis (Upstash) | rankings de produtos registrados e vencidos, geral ou por UF, atualizados pelo Core |
| Memória | só em RAM, por empresa + sessão (últimas 20 mensagens); reiniciar o servidor apaga. Não há memória entre sessões |

O endpoint `GET /api/rankings/products` retorna os rankings `registered` e `expired`, com até cinco
produtos em cada lista. `?state=SP` seleciona o ranking estadual. Cada produto contém `productId`,
`productName` e `score`: o Redis guarda o ID e a pontuação; uma consulta ao PostgreSQL resolve os nomes
dos dois rankings usando a conexão `PGSQL_URL`, que precisa de permissão de leitura em `public.food`.
Membros que não sejam IDs válidos ou não existam no catálogo não são exibidos. Ausência de dados retorna
listas vazias; falha de acesso ao Redis ou PostgreSQL retorna HTTP 503. `registered` conta cadastros de
itens no estoque, não consumo. O ranking estadual não recebe valores do ranking geral como substituição.

## Observabilidade

- **Terminal:** cada `POST /chat` gera linhas `[req=<id>]` com início, fim e tempo de cada etapa (auth/Postgres,
  memória, guardrails, cada chamada ao Gemini com tokens e tamanho da entrada, embedding, Qdrant, MongoDB,
  conferência, gravação da memória) e um resumo que separa o tempo por serviço externo:
  `requisicao.fim status=200 total_ms=2245.6 gemini_ms=2082.5(2x) mongodb_ms=0.3(1x) postgres_ms=120.2(1x) backend_ms=42.6`.
  O mesmo id volta no header `X-Request-Id`. Nunca loga pergunta, resposta, chaves ou senhas (só tamanhos).
  `LOG_LEVEL=DEBUG` mostra também cada tentativa HTTP ao Gemini.
- **LangSmith:** com `LANGSMITH_TRACING=true`, cada pergunta vira uma árvore no projeto `ceris-ms-ia-bi`
  (orquestrador → agente, Gemini, tools e conferência de números).
- **MongoDB:** coleções próprias do web, separadas das do mobile e ligadas pelo `trace_id`:
  `metrics_bi` (uma por pergunta) e `tool_metrics_bi` (uma por chamada de tool).
- **`GET /admin/metrics`:** a página do BI IA no painel do administrador, no mesmo formato da página da IA do
  mobile. Além do que já era gravado, cada pergunta passa a dizer se o guardrail de saída bloqueou e se o erro
  foi de cota do Gemini (429).
- **`GET /admin/roi`:** custo para 100 e 1000 usuários/semana, latência de cada agente e total, índice de
  erros, custo por resolução e ROI. O dólar vem da PTAX do Banco Central. As premissas mudam pela URL, ex.:
  `/admin/roi?days=30&analyst_hour_brl=80`.

## Estrutura

```
app/
  app.py, config.py   API e variáveis do .env
  controller/         rotas (só chamam os services)
  services/           chat, FAQ (ingestão), relatório de métricas e painel do administrador
  core/               assistente, orquestrador, memória e erros
  core/prompts/       prompt do assistente, regras de segurança e descrições das tools
  tools/              tools (relatórios, FAQ) e conferência de números
  guardrails/         regras de entrada e saída
  auth/               X-API-Key e JWT
  repository/         Qdrant, MongoDB e PostgreSQL
  observability/      logs por requisição (trace.py), custo e métricas
  model/              LLM e embeddings (Gemini)
  schemas/            contratos da API e entre agentes
```

## Containers e Kubernetes

Consulte o [guia de containers e Kubernetes](docs/containers.md) para build, configuração e execução em qualquer cluster.
