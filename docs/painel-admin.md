# Painel do administrador

Rotas que o painel do administrador (React) consome para montar a página do BI IA. São só dados em JSON: a
apresentação é do painel. As chaves do JSON são as mesmas da página da IA do mobile (NexUs-AI), para o
painel desenhar as duas com os mesmos componentes; o que não existe aqui vem `null` ou zero, como descrito
abaixo.

## Autenticação

Uma chave só, a mesma em todos os serviços do NexUs (Auth, Core, Notify, IA e BI IA). O painel pede a
chave no login e a manda em todas as requisições:

```
X-Admin-Key: <ADMIN_API_KEY>
```

| Situação | Resposta |
| --- | --- |
| Chave certa | `200` |
| Chave ausente ou errada | `401` |
| `ADMIN_API_KEY` não configurada no servidor | `503` |

A chave do painel não abre o `/chat`, e a `API_KEY` das empresas não abre o painel.

## Rotas

| Método | Rota | Fonte | O que devolve |
| --- | --- | --- | --- |
| `GET` | `/admin/session` | — | Confirma a chave no login: `{"servico", "autenticado", "verificado_em"}` |
| `GET` | `/admin/metrics?dias=7` | MongoDB | Resumo, desempenho, custo e qualidade |
| `GET` | `/admin/report?dias=7` | MongoDB | O período contra o período anterior de mesmo tamanho |
| `GET` | `/admin/langsmith?dias=7` | LangSmith | Execuções por dia, p50/p99 por chain e por agente, feedback |
| `GET` | `/admin/roi` | MongoDB | Custo, cenários e ROI em reais (era `GET /metrics/report`) |

`dias` vai de 1 a 90. `/admin/langsmith` pagina a API do LangSmith e pode levar dezenas de segundos; o
painel deve carregá-la à parte. Os dias são contados no horário de Brasília.

## `/admin/metrics` e `/admin/report`

Mesmo formato da página da IA (veja o `docs/painel-admin.md` do NexUs-AI), com estas diferenças:

| Campo | No BI IA |
| --- | --- |
| `servico` | `ceris-bi-ia` |
| `leitura_nota` | `null`: o BI não lê nota fiscal |
| `desempenho.latencia_por_no[].etapas_s` | `roteador` (router), `agente` (specialist), `juiz` (judge), `guardrails` (input_guardrail + finish). Não há orquestrador separado: vem `0` |
| `qualidade.juiz` | `aprovado` e `devolvido`, reconstruídos das tentativas: cada tentativa do especialista é julgada uma vez. `revertido` é sempre `0`: o BI não tem segunda opinião do juiz |
| `qualidade.guardrails.entrada` | perguntas com rota `blocked` |
| `qualidade.guardrails.saida` | respostas trocadas pelo guardrail de saída (gravado a partir desta versão) |
| `custo.tokens.limite_diario` | `DAILY_TOKEN_LIMIT`, ou `null` quando 0: o plano pago do Gemini não tem teto diário |
| `custo.erros_de_cota` | perguntas que terminaram em 429 / `RESOURCE_EXHAUSTED` do Gemini |

## `/admin/langsmith`

```json
{
  "projeto": "ceris-ms-ia-bi",
  "disponivel": true,
  "periodo": {"inicio": "...", "fim": "..."},
  "execucoes_por_dia": [{"dia": "2026-10-20", "execucoes": 620, "erros": 13, "taxa_erro_pct": 2.1}],
  "latencia_por_chain": [{"nome": "judge", "chamadas": 600, "p50_s": 0.6, "p99_s": 2.4}],
  "latencia_por_agente": [{"nome": "analyst", "chamadas": 300, "p50_s": 1.1, "p99_s": 4.0}],
  "feedback": {"disponivel": true, "total": 0, "por_chave": {}}
}
```

- As chains são os nós do grafo (`input_guardrail`, `router`, `specialist`, `judge`, `finish`).
- Os três especialistas são um nó só no LangSmith, então a latência por agente sai do tempo do `specialist`
  gravado no MongoDB, separado por rota.
- Sem LangSmith (sem chave, tracing desligado ou API fora), a resposta vem com `"disponivel": false` e o
  motivo em `erro`; a latência por agente continua, porque vem do MongoDB.

## Variáveis

| Variável | Uso |
| --- | --- |
| `ADMIN_API_KEY` | Chave do painel |
| `DAILY_TOKEN_LIMIT` | Teto diário desenhado no gráfico de tokens (0 = sem teto) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` | Seção do LangSmith |

```sh
curl -H 'X-Admin-Key: <ADMIN_API_KEY>' 'http://localhost:8000/admin/metrics?dias=7'
```
