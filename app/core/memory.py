"""Short-term memory: one history per session, alive only while the process (server) is running.

Nothing is written to disk or a database. Restarting the server wipes everything, and a new session
starts empty: there is no memory across sessions.
"""
import threading

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

MAX_MESSAGES = 20  # window: only the last N messages go into the prompt


class SessionHistory:
    def __init__(self) -> None:
        self._messages: list[BaseMessage] = []

    @property
    def messages(self) -> list[BaseMessage]:
        return self._messages[-MAX_MESSAGES:]

    def add_user_message(self, text: str) -> None:
        self._messages.append(HumanMessage(content=text))

    def add_ai_message(self, text: str) -> None:
        self._messages.append(AIMessage(content=text))


# Message history of each session, keyed by session_id. Messages run in worker threads, hence the lock.
store: dict[str, SessionHistory] = {}
_lock = threading.Lock()


def get_session_history(session_id: str) -> SessionHistory:
    """Return the history of a session (creates it if it does not exist)."""
    with _lock:
        return store.setdefault(session_id, SessionHistory())


def clear_session(session_id: str) -> None:
    with _lock:
        store.pop(session_id, None)
