"""FAQ retriever tool used by the FAQ agent: semantic search in the FAQ indexed in Qdrant."""
from langchain_core.tools import StructuredTool

from app.config import FAQ_TOP_K
from app.core.prompts.tools import (
    FAQ_NOT_INDEXED,
    FAQ_OUTDATED,
    NO_FAQ,
    SEARCH_FAQ_DESCRIPTION,
)
from app.repository.faq_repository import count_faq_items, search_faq


def _format(items: list[dict]) -> str:
    return "\n\n".join(f"P: {i.get('question', '')}\nR: {i.get('answer', '')}" for i in items)


def search_faq_tool(query: str) -> str:
    found = search_faq(query, FAQ_TOP_K)
    items = [i for i in found if i.get("question") and i.get("answer")]
    if items:
        return _format(items)
    if found:
        # Items exist but without question/answer: collection indexed by an old version of the code
        print(f"[faq] ATENÇÃO: {FAQ_OUTDATED}")
        return FAQ_OUTDATED
    # The search always returns the closest items; an empty result means the FAQ was never indexed.
    if count_faq_items() == 0:
        print(f"[faq] ATENÇÃO: {FAQ_NOT_INDEXED}")
        return FAQ_NOT_INDEXED
    return NO_FAQ


def build_faq_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(search_faq_tool, name="search_faq", description=SEARCH_FAQ_DESCRIPTION)]
