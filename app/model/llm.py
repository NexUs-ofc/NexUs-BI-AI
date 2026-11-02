"""LLM factory. To switch providers, change only this file.

Quick key/model check (run from the project root):
    python -m app.model.llm
"""
from __future__ import annotations

import re
import uuid
from typing import Any, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr

from app.config import GOOGLE_API_KEY, LLM_MODEL, LLM_TEMPERATURE

# Module-level client cache: creating a new genai.Client() on every call
# adds TCP/TLS setup overhead. One shared instance is safe (thread-safe).
_GENAI_CLIENT: Any = None
_GENAI_ASYNC_CLIENT: Any = None


def _get_client(api_key: str) -> Any:
    global _GENAI_CLIENT
    from google import genai as google_genai
    if _GENAI_CLIENT is None:
        _GENAI_CLIENT = google_genai.Client(api_key=api_key)
    return _GENAI_CLIENT


def _get_async_client(api_key: str) -> Any:
    global _GENAI_ASYNC_CLIENT
    from google import genai as google_genai
    if _GENAI_ASYNC_CLIENT is None:
        _GENAI_ASYNC_CLIENT = google_genai.Client(api_key=api_key).aio
    return _GENAI_ASYNC_CLIENT


# ---------------------------------------------------------------------------
# ChatGoogleInteractions – wrapper for gemini-3.x+ (requires Interactions API)
# ---------------------------------------------------------------------------

class ChatGoogleInteractions(BaseChatModel):
    """LangChain ChatModel backed by Google's Interactions API.

    Required for gemini-3.x+ models; the old `generate_content` endpoint
    returns 504 for those models.
    """

    model_name: str = Field(..., alias="model")
    temperature: float = 0.2
    google_api_key: str = ""
    max_retries: int = 1
    timeout: Optional[int] = 120
    # Raw LangChain tools stored by bind_tools()
    _bound_tools: List[Any] = PrivateAttr(default_factory=list)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    # --- Tool binding ---------------------------------------------------

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ChatGoogleInteractions":
        """Return a copy of this model with tools pre-bound."""
        copy = ChatGoogleInteractions(
            model=self.model_name,
            temperature=self.temperature,
            google_api_key=self.google_api_key,
            max_retries=self.max_retries,
            timeout=self.timeout,
        )
        copy._bound_tools = list(tools)
        return copy

    # --- Message conversion ---------------------------------------------

    def _to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                p.get("text", str(p)) if isinstance(p, dict) else str(p)
                for p in content
            )
        return str(content)

    def _messages_to_steps(self, messages: List[BaseMessage]) -> tuple[str, list]:
        """Return (system_instruction, [steps]) for the Interactions API."""
        system = ""
        steps: list = []
        # Map call_id → tool_name so ToolMessage can always fill in `name`
        call_id_to_name: dict[str, str] = {}

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system = self._to_text(msg.content)

            elif isinstance(msg, HumanMessage):
                steps.append({
                    "type": "user_input",
                    "content": [{"type": "text", "text": self._to_text(msg.content)}],
                })

            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        call_id = tc.get("id") or str(uuid.uuid4())
                        call_id_to_name[call_id] = tc["name"]
                        steps.append({
                            "type": "function_call",
                            "id": call_id,
                            "name": tc["name"],
                            "arguments": tc.get("args", {}),
                        })
                else:
                    text = self._to_text(msg.content)
                    if text:
                        steps.append({
                            "type": "model_output",
                            "content": [{"type": "text", "text": text}],
                        })

            elif isinstance(msg, ToolMessage):
                # `name` is required by the Interactions API; fall back to
                # the name stored when we processed the matching function_call.
                name = (
                    getattr(msg, "name", None)
                    or call_id_to_name.get(msg.tool_call_id, "")
                )
                step: dict = {
                    "type": "function_result",
                    "call_id": msg.tool_call_id,
                    "result": self._to_text(msg.content),
                }
                if name:
                    step["name"] = name
                steps.append(step)

        return system, steps

    @staticmethod
    def _flatten_schema(schema: dict) -> dict:
        """Inline $ref / $defs and strip fields the Interactions API rejects."""
        import copy as _copy
        schema = _copy.deepcopy(schema)
        defs = {**schema.pop("$defs", {}), **schema.pop("definitions", {})}

        def resolve(obj: Any) -> Any:
            if isinstance(obj, list):
                return [resolve(v) for v in obj]
            if not isinstance(obj, dict):
                return obj
            # Inline $ref
            if "$ref" in obj:
                ref_key = obj["$ref"].split("/")[-1]
                return resolve(_copy.deepcopy(defs.get(ref_key, {})))
            # Flatten allOf with a single $ref (Pydantic v2 pattern)
            if "allOf" in obj and len(obj["allOf"]) == 1:
                merged = resolve(obj["allOf"][0])
                if isinstance(merged, dict):
                    for k, v in obj.items():
                        if k != "allOf":
                            merged.setdefault(k, v)
                return merged
            return {k: resolve(v) for k, v in obj.items()}

        flat = resolve(schema)
        for key in ("title", "$schema"):
            flat.pop(key, None)
        # Remove title from nested properties (Gemini complains)
        for prop in flat.get("properties", {}).values():
            if isinstance(prop, dict):
                prop.pop("title", None)
        return flat

    def _format_tools(self, tools: List[Any]) -> list:
        """Convert LangChain tools to Interactions API function descriptors."""
        result = []
        for tool in tools:
            if not (hasattr(tool, "name") and hasattr(tool, "description")):
                continue
            params: dict = {"type": "object", "properties": {}}
            raw: dict | None = None
            schema_src = getattr(tool, "args_schema", None)
            if schema_src is not None:
                try:
                    if isinstance(schema_src, dict):
                        raw = schema_src
                    elif hasattr(schema_src, "model_json_schema"):
                        raw = schema_src.model_json_schema()
                    elif hasattr(schema_src, "schema"):
                        raw = schema_src.schema()
                except Exception:  # noqa: BLE001
                    pass
            if raw:
                params = self._flatten_schema(raw)
            result.append({
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": params,
            })
        return result

    # --- Core generation ------------------------------------------------

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        client = _get_client(self.google_api_key)
        system, steps = self._messages_to_steps(messages)

        # Tools can arrive via bind_tools() OR via Runnable.bind(tools=...)
        extra_tools: list = kwargs.pop("tools", None) or []
        all_tools = list(self._bound_tools) + list(extra_tools)

        api_kwargs: dict = {
            "model": self.model_name,
            "input": steps if steps else "",
        }
        if system:
            api_kwargs["system_instruction"] = system
        if self.temperature > 0.0:
            api_kwargs["generation_config"] = {"temperature": self.temperature}
        if all_tools:
            api_kwargs["tools"] = self._format_tools(all_tools)

        timeout_s = self.timeout or 60
        import datetime as _dt
        _t0 = _dt.datetime.now()
        print(f"[{_t0.strftime('%H:%M:%S.%f')[:-3]}] [llm._generate] interactions.create(model={self.model_name}, timeout={timeout_s}s, tools={[t.name for t in all_tools if hasattr(t,'name')]})", flush=True)
        response = client.interactions.create(**api_kwargs, timeout=timeout_s)
        _elapsed = (_dt.datetime.now() - _t0).total_seconds()
        print(f"[{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [llm._generate] resposta em {_elapsed:.2f}s — output_text={repr((response.output_text or '')[:80])}", flush=True)

        # Parse function calls from response steps
        tool_calls: list = []
        if hasattr(response, "steps") and response.steps:
            for step in response.steps:
                if getattr(step, "type", None) == "function_call":
                    tool_calls.append({
                        "id": getattr(step, "id", str(uuid.uuid4())),
                        "name": step.name,
                        "args": getattr(step, "arguments", {}) or {},
                        "type": "tool_call",
                    })

        text = response.output_text or ""
        ai_msg = (
            AIMessage(content=text, tool_calls=tool_calls)
            if tool_calls
            else AIMessage(content=text)
        )
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async version of _generate using client.aio.interactions.create()."""
        client = _get_async_client(self.google_api_key)
        system, steps = self._messages_to_steps(messages)

        extra_tools: list = kwargs.pop("tools", None) or []
        all_tools = list(self._bound_tools) + list(extra_tools)

        api_kwargs: dict = {
            "model": self.model_name,
            "input": steps if steps else "",
        }
        if system:
            api_kwargs["system_instruction"] = system
        if self.temperature > 0.0:
            api_kwargs["generation_config"] = {"temperature": self.temperature}
        if all_tools:
            api_kwargs["tools"] = self._format_tools(all_tools)

        timeout_s = self.timeout or 60
        import datetime as _dt
        _t0 = _dt.datetime.now()
        print(f"[{_t0.strftime('%H:%M:%S.%f')[:-3]}] [llm._agenerate] interactions.create(model={self.model_name}, timeout={timeout_s}s, tools={[t.name for t in all_tools if hasattr(t,'name')]})", flush=True)
        response = await client.interactions.create(**api_kwargs, timeout=timeout_s)
        _elapsed = (_dt.datetime.now() - _t0).total_seconds()
        print(f"[{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] [llm._agenerate] resposta em {_elapsed:.2f}s — output_text={repr((response.output_text or '')[:80])}", flush=True)

        tool_calls: list = []
        if hasattr(response, "steps") and response.steps:
            for step in response.steps:
                if getattr(step, "type", None) == "function_call":
                    tool_calls.append({
                        "id": getattr(step, "id", str(uuid.uuid4())),
                        "name": step.name,
                        "args": getattr(step, "arguments", {}) or {},
                        "type": "tool_call",
                    })

        text = response.output_text or ""
        ai_msg = (
            AIMessage(content=text, tool_calls=tool_calls)
            if tool_calls
            else AIMessage(content=text)
        )
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    @property
    def _llm_type(self) -> str:
        return "google-interactions"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _uses_interactions_api(model: str) -> bool:
    """Return True for gemini-3.x+ that require the Interactions API."""
    m = re.match(r"gemini-(\d+)", model)
    return bool(m and int(m.group(1)) >= 3)


def get_llm(temperature: float | None = None) -> BaseChatModel:
    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY não definida. Preencha o arquivo .env (veja .env.example)."
        )
    temp = LLM_TEMPERATURE if temperature is None else temperature

    if _uses_interactions_api(LLM_MODEL):
        return ChatGoogleInteractions(
            model=LLM_MODEL,
            temperature=temp,
            google_api_key=GOOGLE_API_KEY,
            max_retries=1,
            timeout=120,
        )

    # Fallback for gemini-2.x and older
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=temp,
        google_api_key=GOOGLE_API_KEY,
        max_retries=1,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

def is_quota_error(error: Exception | None) -> bool:
    """Gemini refused the call for quota or rate limit (HTTP 429)."""
    if error is None:
        return False
    msg = str(error)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()


def explain_error(error: Exception) -> str:
    """Translate the most common Gemini API errors into a readable message."""
    msg = str(error)
    if is_quota_error(error):
        return (
            f"Limite/cota da API atingido para o modelo '{LLM_MODEL}'. "
            f"Espere um pouco ou troque LLM_MODEL no .env. Detalhe: {msg[:300]}"
        )
    if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
        return (
            f"Modelo '{LLM_MODEL}' sobrecarregado. Tente de novo. Detalhe: {msg[:300]}"
        )
    if "API_KEY_INVALID" in msg or "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
        return f"Chave de API inválida ou sem permissão. Detalhe: {msg[:300]}"
    if "404" in msg or "NOT_FOUND" in msg:
        return (
            f"Modelo '{LLM_MODEL}' não encontrado para esta chave. "
            f"Troque LLM_MODEL no .env. Detalhe: {msg[:300]}"
        )
    if "504" in msg or "DEADLINE_EXCEEDED" in msg:
        return f"Timeout na API do Gemini. Tente novamente. Detalhe: {msg[:300]}"
    return f"{type(error).__name__}: {msg[:500]}"


if __name__ == "__main__":
    print(f"Testando modelo '{LLM_MODEL}' (chave começa com '{GOOGLE_API_KEY[:6]}...')")
    try:
        print("OK ->", get_llm().invoke("Responda apenas: ok").content)
    except Exception as error:  # noqa: BLE001
        print("FALHOU ->", explain_error(error))
