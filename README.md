# NexUs BI AI — assistente multiagente (API)

```
POST /chat → controller → service → Orquestrador
   Guardrail de entrada → Roteador → [FAQ (Qdrant) | Analista descritivo | Recomendador | fora de escopo]
   → Juiz (refaz se reprovar) → Guardrail de saída → memória da sessão → resposta
```

| Agente | Arquivo | Papel |
|---|---|---|
| Guardrails | `app/guardrails/guardrails.py` | Regras fixas (regex): bloqueia injeção de prompt e pedidos ilegais; mascara CPF/CNPJ/cartão/e-mail/telefone na entrada e na saída |
| Roteador | `app/core/roteador.py` | LLM com saída estruturada que escolhe `faq`, `analista`, `recomendador` ou `fora_escopo` |
| FAQ | `app/core/faq.py` | Busca os itens mais parecidos no Qdrant e responde só com eles |
| Analista descritivo | `app/core/analista.py` | Descreve os dados da empresa (fonte de dados ainda não conectada) |
| Recomendador | `app/core/recomendador.py` | Percepções e insights; deixa explícito que não toma decisões |
| Orquestrador | `app/core/orquestrador.py` | Coordena o fluxo, reenvia o feedback do Juiz e grava a memória |
| Juiz | `app/core/juiz.py` | LLM-as-a-judge: reprova alucinação, desvio de papel e PII |

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
  schemas/                      # agentes.py (entre agentes) e api.py (contratos HTTP)
  static/faq.json               # FAQ de origem para a ingestão (vazio)
  tools/ observability/         # ainda não implementados
```

Memória: `app/core/memory.py`, apenas em RAM e por sessão (`session_id`). Reiniciar o servidor apaga tudo.

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env                 # preencha GOOGLE_API_KEY, API_KEY e QDRANT_URL
python -m app.services.faq_service   # indexa o app/static/faq.json no Qdrant
uvicorn app.app:app --reload         # docs em http://localhost:8000/docs
```

Teste rápido da chave/modelo do Gemini: `python -m app.model.llm`.

## Endpoints

Todos em `/chat` exigem o header `X-API-Key` com o valor de `API_KEY` do `.env`.

| Método | Rota | O que faz |
|---|---|---|
| POST | `/chat` | Recebe `{"pergunta": "...", "session_id": "opcional", "debug": false}` e devolve `{"session_id", "resposta", "rota", "passos"}` |
| DELETE | `/chat/{session_id}` | Apaga a memória da sessão |
| GET | `/health` | Status e variáveis faltando (sem autenticação) |

```bash
curl -X POST http://localhost:8000/chat -H "X-API-Key: SUA_CHAVE" -H "Content-Type: application/json" \
     -d '{"pergunta": "oi", "debug": true}'
```

Para manter a conversa, reenvie o `session_id` devolvido na primeira resposta.

## FAQ

Edite `app/static/faq.json` e rode `python -m app.services.faq_service` (recria a collection):

```json
[
  {"pergunta": "O que é o NexUs BI?", "resposta": "..."}
]
```

## Dados para o Analista e o Recomendador

As tools de acesso a dados ainda não foram definidas. Quando forem, busque os dados no ponto marcado com
`TODO` em `app/core/orquestrador.py` e passe pelo parâmetro `dados` de `agente_analista` / `agente_recomendador`.
Sem dados, os dois agentes avisam que a base ainda não está conectada.
