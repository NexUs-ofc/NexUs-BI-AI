"""FAQ retriever tool: semantic search in the FAQ indexed in Qdrant (embedding of the query + vector search).

If Qdrant or the embedding fails, or the collection was never indexed, the tool raises ExternalServiceError:
the chat answers with a clear error instead of letting the model answer from "general knowledge".
"""
from langchain_core.tools import StructuredTool

from app.config import FAQ_TOP_K
from app.core.errors import ExternalServiceError
from app.core.prompts.tools import NO_FAQ, SEARCH_FAQ_DESCRIPTION
from app.observability import trace
from app.observability.trace import redact
from app.repository.faq_repository import count_faq_items, search_faq

FAQ_SETUP_HINT = "rode `python -m app.services.faq_service` para indexar o app/static/faq.json"


def _format(items: list[dict]) -> str:
    return "\n\n".join(f"P: {i['question']}\nR: {i['answer']}" for i in items)


def search_faq_tool(query: str) -> str:
    with trace.step("tool.search_faq", chars_consulta=len(query)) as info:
        try:
            found = search_faq(query, FAQ_TOP_K)
        except ExternalServiceError:
            raise
        except Exception as error:  # network, auth, collection...
            raise ExternalServiceError("Qdrant", f"a busca no FAQ falhou ({redact(error, 150)}).") from error
        items = [i for i in found if i.get("question") and i.get("answer")]
        info.update(encontrados=len(found), usados=len(items),
                    melhor_score=max((i.get("score", 0) for i in items), default=None))
        if items:
            return _format(items)
        if found:
            raise ExternalServiceError("Qdrant", f"a collection do FAQ está num formato antigo; {FAQ_SETUP_HINT}.")
        if count_faq_items() == 0:
            raise ExternalServiceError("Qdrant", f"o FAQ não está indexado; {FAQ_SETUP_HINT}.")
        return NO_FAQ


def build_faq_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(search_faq_tool, name="search_faq", description=SEARCH_FAQ_DESCRIPTION)]
