"""FAQ retriever tool used by the FAQ agent: semantic search in the FAQ indexed in Qdrant."""
from langchain_core.tools import StructuredTool

from app.config import FAQ_TOP_K
from app.core.prompts.tools import (
    FAQ_NOT_INDEXED,
    FAQ_OUTDATED,
    NO_FAQ,
    QDRANT_UNAVAILABLE,
    SEARCH_FAQ_DESCRIPTION,
)
from app.repository.faq_repository import count_faq_items, search_faq


def _format(items: list[dict]) -> str:
    return "\n\n".join(f"P: {i.get('question', '')}\nR: {i.get('answer', '')}" for i in items)


def search_faq_tool(query: str) -> str:
    # DIAGNÓSTICO: Qdrant desativado temporariamente para isolar o problema do chat.
    # Para reativar, remova as duas linhas abaixo.
    import datetime as _dt; print(f"[{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [faq_tool] Qdrant DESATIVADO — retornando indisponível", flush=True)
    return QDRANT_UNAVAILABLE

    try:  # noqa: unreachable
        found = search_faq(query, FAQ_TOP_K)
    except Exception as exc:
        # Qdrant indisponível (não iniciado, cota esgotada, etc.) — degrada em vez de derrubar o chat.
        print(f"[faq] Qdrant inacessível: {exc}")
        return QDRANT_UNAVAILABLE
    items = [i for i in found if i.get("question") and i.get("answer")]
    if items:
        return _format(items)
    if found:
        print(f"[faq] ATENÇÃO: {FAQ_OUTDATED}")
        return FAQ_OUTDATED
    if count_faq_items() == 0:
        print(f"[faq] ATENÇÃO: {FAQ_NOT_INDEXED}")
        return FAQ_NOT_INDEXED
    return NO_FAQ


def build_faq_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(search_faq_tool, name="search_faq", description=SEARCH_FAQ_DESCRIPTION)]
