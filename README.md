# NexUs BI AI — assistente multiagente (API)

```
POST /chat → controller → service → Orquestrador
   Guardrail de entrada → Roteador → [FAQ (Qdrant) | Analista descritivo | Recomendador | fora de escopo]
   → Juiz (refaz se reprovar) → Guardrail de saída → memória da sessão → resposta
```

| Agente | Arquivo | Papel |
|---|---|---|
| Guardrails | `app/guardrails/guardrails.py` | Regras fixas (regex): bloqueia injeção de prompt e pedidos ilegais; mascara CPF/CNPJ/cartão/e-mail/telefone na entrada e na saída |
| Roteador | `app/core/router.py` | LLM com saída estruturada que escolhe `faq`, `analyst`, `recommender` ou `out_of_scope` |
| FAQ | `app/core/faq.py` | Busca os itens mais parecidos no Qdrant e responde só com eles |
| Analista descritivo | `app/core/analyst.py` | Descreve os dados lendo os relatórios consolidados do MongoDB (tools de relatórios) |
| Recomendador | `app/core/recommender.py` | Percepções e insights a partir dos relatórios; deixa explícito que não toma decisões |
| Orquestrador | `app/core/orchestrator.py` | Coordena o fluxo, reenvia o feedback do Juiz e grava a memória |
| Juiz | `app/core/judge.py` | LLM-as-a-judge: reprova alucinação, desvio de papel e PII |

## Estrutura

```
app/
  app.py                        # cria a API FastAPI e registra os controllers
  config.py                     # variáveis do .env
  auth/api_key.py               # proteção das rotas (header X-API-Key)
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

Todos em `/chat` exigem o header `X-API-Key` com o valor de `API_KEY` do `.env`.

| Método | Rota | O que faz |
|---|---|---|
| POST | `/chat` | Recebe `{"question": "...", "session_id": "opcional", "company_id": "opcional", "debug": false}` e devolve `{"session_id", "answer", "route", "steps"}` |
| DELETE | `/chat/{session_id}` | Apaga a memória da sessão |
| GET | `/health` | Status e variáveis faltando (sem autenticação) |

```bash
curl -X POST http://localhost:8000/chat -H "X-API-Key: SUA_CHAVE" -H "Content-Type: application/json" \
     -d '{"question": "oi", "debug": true}'
```

Para manter a conversa, reenvie o `session_id` devolvido na primeira resposta.

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

- A empresa (`company_id`) vem do corpo do `POST /chat`, nunca da LLM: assim o modelo não consegue ler relatórios de outra empresa. Sem `company_id`, todos os relatórios ficam visíveis.
- Cada documento da collection precisa ter os campos `mes`, `ano` e `id_empresa`; o resto do relatório é livre. Banco e collection ficam no `.env` (`MONGODB_*`). Mês e ano podem estar gravados como número ou como texto.
- O que as tools retornam vira o contexto do Juiz, que reprova números que não estejam nos relatórios.
