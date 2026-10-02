# NexUs BI AI — assistente multiagente (CLI)

```
Usuário → Guardrail de entrada → Roteador → [FAQ | Analista descritivo | Recomendador | fora de escopo]
        → Juiz (refaz se reprovar) → Guardrail de saída → memória da sessão → Usuário
```

| Agente | Arquivo | Papel |
|---|---|---|
| Guardrails | `app/guardrails/guardrails.py` | Regras fixas (regex): bloqueia injeção de prompt e pedidos ilegais; mascara CPF/CNPJ/cartão/e-mail/telefone na entrada e na saída |
| Roteador | `app/core/roteador.py` | LLM com saída estruturada que escolhe `faq`, `analista`, `recomendador` ou `fora_escopo` |
| FAQ | `app/core/faq.py` | Responde só com o FAQ estático (`app/static/faq.json`) |
| Analista descritivo | `app/core/analista.py` | Descreve a base; os números são calculados em pandas, a LLM só interpreta |
| Recomendador | `app/core/recomendador.py` | Percepções e insights; deixa explícito que não toma decisões |
| Orquestrador | `app/controller/orquestrador.py` | Coordena o fluxo, reenvia o feedback do Juiz e grava a memória |
| Juiz | `app/core/juiz.py` | LLM-as-a-judge: reprova alucinação, desvio de papel e PII |

Estrutura:

```
app/
  app.py                      # CLI (while True, sai com exit/sair)
  config.py                   # variáveis do .env
  controller/orquestrador.py  # fluxo entre agentes
  core/                       # agentes + memória da sessão (memory.py) + base.py (chain comum)
  guardrails/guardrails.py
  model/llm.py                # fábrica da LLM (Gemini)
  repository/                 # acesso a CSV e FAQ
  schemas/agentes.py          # modelos Pydantic trocados entre agentes
  static/                     # faq.json (vazio) e vendas_exemplo.csv
  tools/                      # tools usadas pelos agentes (resumo da base, FAQ em texto)
  auth/ observability/        # ainda não usados
```

Memória: `app/core/memory.py`, apenas em RAM e por sessão (`session_id` gerado a cada execução). Nada é persistido.

## Como rodar

```bash
pip install -r requirements.txt
cp .env.example .env          # preencha GOOGLE_API_KEY
python -m app.app             # ou: python -m app.app --debug
```

Comandos no chat: `exit`/`sair` encerra, `limpar` apaga a memória da sessão.

## FAQ

`app/static/faq.json` começa vazio (`[]`). Formato:

```json
[
  {"pergunta": "O que é o NexUs BI?", "resposta": "..."}
]
```

## Base de dados

`app/static/vendas_exemplo.csv` é um exemplo fictício. Para trocar, aponte `DATA_PATH` no `.env` para outro CSV
(ou reescreva `app/repository/dados_repository.py` mantendo a mesma assinatura).
