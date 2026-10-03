"""Agente Roteador: decide qual especialista atende a pergunta."""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.model.llm import get_llm
from app.schemas.agentes import DecisaoRota

SYSTEM_PROMPT = """Você é o ROTEADOR de um assistente de BI da empresa NexUs.
Classifique a última mensagem do usuário (use o histórico só para entender o contexto) em UMA rota:

- faq: dúvidas gerais e estáticas (o que é o sistema, como usar, horários, políticas, saudações como "oi").
- analista: perguntas descritivas sobre os dados (quanto, qual, quem vendeu mais, evolução, totais, comparações, médias).
- recomendador: pedidos de sugestão, recomendação, "o que fazer", oportunidades, pontos de atenção.
- fora_escopo: assuntos que não têm relação com a empresa, seus dados ou o uso do sistema.

Responda apenas com a estrutura pedida."""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("historico"),
    ("human", "{usuario}"),
])


def rotear(usuario: str, historico: list) -> DecisaoRota:
    chain = prompt | get_llm(temperature=0).with_structured_output(DecisaoRota)
    try:
        return chain.invoke({"usuario": usuario, "historico": historico})
    except Exception:  # noqa: BLE001 - fallback seguro se a saída estruturada falhar
        return DecisaoRota(rota="faq", motivo="fallback por erro no roteamento")
