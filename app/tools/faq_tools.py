"""FAQ retriever tool used by the FAQ agent: semantic search in the FAQ indexed in Qdrant."""
from langchain_core.tools import StructuredTool

from app.config import FAQ_TOP_K
from app.prompts.tools import FAQ_NOT_INDEXED, NO_FAQ, SEARCH_FAQ_DESCRIPTION
from app.repository.faq_repository import count_faq_items, search_faq


def _format(items: list[dict]) -> str:
    return "\n\n".join(f"P: {i.get('question', '')}\nR: {i.get('answer', '')}" for i in items)


def search_faq_tool(query: str) -> str:
    items = search_faq(query, FAQ_TOP_K)
    if items:
        return _format(items)
    # The search always returns the closest items; an empty result means the FAQ was never indexed.
    if count_faq_items() == 0:
        print(f"[faq] ATENÇÃO: {FAQ_NOT_INDEXED}")
        return FAQ_NOT_INDEXED
    return NO_FAQ


def build_faq_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(search_faq_tool, name="search_faq", description=SEARCH_FAQ_DESCRIPTION)]
