# NexUs BI AI

Assistente multiagente de Business Intelligence (API FastAPI). A empresa pergunta em português e o
sistema responde sobre o NexUs BI ou sobre os relatórios mensais, com um juiz conferindo cada resposta.

**Stack:** Python · FastAPI · LangChain 1.x (`create_agent`) · LangGraph · Gemini · Qdrant · MongoDB · PostgreSQL · LangSmith

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env                    # preencha as variáveis (veja o próprio arquivo)
python -m app.services.faq_service      # carrega o app/static/faq.json no Qdrant
python -m uvicorn app.app:app --reload  # documentação em http://localhost:8000/docs
```

Testes rápidos: `python -m app.model.llm` (chave do Gemini) e `python -m app.core.orchestrator` (desenha o grafo).

## Como chamar a API

As rotas `/chat` exigem dois headers (mesmo esquema do NexUs-AI):

| Header | O que é |
|---|---|
| `X-API-Key` | chave da aplicação (`API_KEY` do `.env`) |
| `Authorization: Bearer <token>` | token do login no site, emitido pelo NexUs-Auth |

O token precisa ser de um perfil **COMPANY** com empresa **ACTIVE** no PostgreSQL do Auth; outros perfis
recebem 403. Para testar sem o site: `python -m app.auth.jwt_handler <profile_id>` gera um token.

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
