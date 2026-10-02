"""Tool usada pelo agente de FAQ: devolve o FAQ como texto para o prompt."""
from app.repository.faq_repository import carregar_faq


def faq_como_texto() -> str:
    itens = carregar_faq()
    if not itens:
        return ""
    return "\n\n".join(f"P: {i.get('pergunta', '')}\nR: {i.get('resposta', '')}" for i in itens)
