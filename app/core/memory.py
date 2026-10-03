"""Memória de curto prazo: vive apenas enquanto o processo (sessão) estiver rodando.

Nada é gravado em disco/banco. Ao sair do programa, tudo é perdido.
"""
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

MAX_MENSAGENS = 20  # janela: só as últimas N mensagens vão para os prompts


class HistoricoSessao:
    def __init__(self) -> None:
        self._mensagens: list[BaseMessage] = []

    @property
    def messages(self) -> list[BaseMessage]:
        return self._mensagens[-MAX_MENSAGENS:]

    def add_user_message(self, texto: str) -> None:
        self._mensagens.append(HumanMessage(content=texto))

    def add_ai_message(self, texto: str) -> None:
        self._mensagens.append(AIMessage(content=texto))


# Dicionário para armazenar o histórico de mensagens de cada sessão
store: dict[str, HistoricoSessao] = {}


def get_session_history(session_id: str) -> HistoricoSessao:
    """Retorna o histórico de uma sessão específica (cria se não existir)."""
    if session_id not in store:
        store[session_id] = HistoricoSessao()
    return store[session_id]


def limpar_sessao(session_id: str) -> None:
    store.pop(session_id, None)
