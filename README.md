# NexUs BI AI — assistente multiagente (API)

```
POST /chat → controller → service → Orquestrador
   Guardrail de entrada → Roteador → [FAQ (Qdrant) | Analista descritivo | Recomendador | fora de escopo]
   → Juiz (refaz se reprovar) → Guardrail de saída → memória da sessão → resposta
```

Todos os agentes (roteador, especialistas e juiz) são criados com `create_agent` do LangChain 1.x
(`app/core/base.py`), que monta o loop ReAct: a LLM decide chamar uma tool, a tool roda e o resultado volta
para a LLM. Limites por pergunta: 4 chamadas de tool e 8 chamadas ao modelo.

| Agente | Arquivo | Papel |
|---|---|---|
| Guardrails | `app/guardrails/guardrails.py` | Regras fixas (regex): bloqueia injeção de prompt e pedidos ilegais; mascara CPF/CNPJ/cartão/e-mail/telefone na entrada e na saída |
| Roteador | `app/core/router.py` | `create_agent` com saída estruturada (`RouteDecision`) que escolhe `faq`, `analyst`, `recommender` ou `out_of_scope` |
| FAQ | `app/core/faq.py` | Consulta o FAQ no Qdrant pela tool `search_faq` e responde com base nele |
| Analista descritivo | `app/core/analyst.py` | Descreve os dados lendo os relatórios consolidados do MongoDB (tools de relatórios) |
| Recomendador | `app/core/recommender.py` | Percepções e insights a partir dos relatórios; deixa explícito que não toma decisões |
| Orquestrador | `app/core/orchestrator.py` | Coordena o fluxo, reenvia o feedback do Juiz e grava a memória |
| Juiz | `app/core/judge.py` | LLM-as-a-judge com tools de validação (`check_numbers_against_context`, `search_context`): reprova alucinação, desvio de papel e PII; aprova só com nota ≥ 7 |

## Estrutura

```
app/
  app.py                        # cria a API FastAPI e registra os controllers
  config.py                     # variáveis do .env
  auth/api_key.py               # header X-API-Key (aplicação cliente)
  auth/jwt_handler.py           # validação do JWT emitido pelo NexUs-Auth
  auth/dependencies.py          # get_current_user: X-API-Key + JWT + empresa ativa no Postgres
  repository/company_repository.py # consulta a empresa no PostgreSQL do Auth
  controller/chat_controller.py # endpoints: só chamam os services
  services/chat_service.py      # ponte entre a API e o Orquestrador
  services/faq_service.py       # ingestão do FAQ no Qdrant
  core/                         # agentes, orquestrador e memória da sessão
  prompts/                      # um arquivo de prompt por agente
  guardrails/guardrails.py
  model/llm.py                  # fábrica da LLM (Gemini)
  model/embeddings.py           # embeddings do FAQ
  repository/faq_repository.py  # acesso ao Qdrant
  repository/report_repository.py # leitura dos relatórios no MongoDB
  schemas/                      # agents.py (entre agentes) e api.py (contratos HTTP)
  static/faq.json               # FAQ de origem para a ingestão (vazio)
  tools/report_tools.py         # tools de relatórios usadas pelo analista e pelo recomendador
  tools/faq_tools.py            # tool search_faq (FAQ retriever)
  tools/judge_tools.py          # tools de validação do juiz (sem LLM)
  observability/                # ainda não implementado
```

Memória: `app/core/memory.py`, apenas em RAM e por sessão (`session_id`). Reiniciar o servidor apaga tudo.

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env                 # preencha GOOGLE_API_KEY, API_KEY e QDRANT_URL
python -m app.services.faq_service   # indexa o app/static/faq.json no Qdrant
python -m uvicorn app.app:app --reload  # docs em http://localhost:8000/docs
```

Teste rápido da chave/modelo do Gemini: `python -m app.model.llm`.

## Endpoints

Todos em `/chat` exigem dois headers (mesmo esquema do NexUs-AI):
- `X-API-Key`: valor de `API_KEY` do `.env`;
- `Authorization: Bearer <token>`: access token que o NexUs-Auth devolve no login do site (`channel: PLATFORM`).
  É validado aqui com `JWT_SECRET_BASE64` (mesmo segredo do Auth): assinatura, validade e emissor `nexus-auth`.

Regra do MVP: o relatório é o mesmo para todas as empresas. A autenticação só garante que quem pergunta é
uma empresa real: o token precisa ser de um perfil `COMPANY` e a empresa precisa existir e estar `ACTIVE` no
PostgreSQL do Auth (`PGSQL_URL`, tabelas `profile` e `company`). Outros perfis (ADMIN, HOUSEHOLD) recebem 403.
O CORS está liberado para o site chamar a API pelo navegador.

Para testar sem fazer login no site, gere um token de desenvolvimento com o id de um perfil de empresa
ativo no banco do Auth: `python -m app.auth.jwt_handler <profile_id>`.
No `/docs`, clique em **Authorize** e preencha os dois campos.

| Método | Rota | O que faz |
|---|---|---|
| POST | `/chat` | Recebe `{"question": "...", "session_id": "opcional", "debug": false}` e devolve `{"session_id", "answer", "route", "steps"}` |
| DELETE | `/chat/{session_id}` | Apaga a memória da sessão (da empresa do token) |
| GET | `/health` | Status e variáveis faltando (sem autenticação) |

```bash
curl -X POST http://localhost:8000/chat -H "X-API-Key: SUA_CHAVE" -H "Authorization: Bearer SEU_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"question": "oi", "debug": true}'
```

Para manter a conversa, reenvie o `session_id` devolvido na primeira resposta. A memória fica só em RAM
e é separada por empresa + sessão: outra sessão (ou outra empresa com o mesmo id) começa sem histórico.

## FAQ

Edite `app/static/faq.json` e rode `python -m app.services.faq_service` (recria a collection):

```json
[
  {"question": "O que é o NexUs BI?", "answer": "..."}
]
```

## Relatórios (Analista e Recomendador)

Os dois agentes leem os relatórios consolidados mensais já salvos no MongoDB, por duas tools
(`app/tools/report_tools.py`), escolhidas pela própria LLM:

| Tool | Quando é usada | Parâmetros |
|---|---|---|
| `search_reports_by_period` | O usuário citou mês, ano ou período ("maio de 2026", "1º trimestre", "mês passado") | `start_month`, `start_year`, `end_month` e `end_year` (opcionais, para intervalos) |
| `get_latest_reports` | O usuário não citou período | `limit` (padrão `REPORTS_LATEST_LIMIT`) |

- Existe um relatório por mês, o mesmo para todas as empresas (as tools não filtram por empresa).
- Cada documento da collection precisa ter os campos `mes` e `ano`; o resto do relatório é livre. Banco e collection ficam no `.env` (`MONGODB_*`). Mês e ano podem estar gravados como número ou como texto.
- O que as tools retornam vira o contexto do Juiz, que reprova números que não estejam nos relatórios.
