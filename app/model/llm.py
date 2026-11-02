"""LLM factory. To switch providers, change only this file.

Quick key/model check, with the time of each call (run from the project root):
    python -m app.model.llm
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field, PrivateAttr

from app.config import (
    GOOGLE_API_KEY,
    LLM_FALLBACK_MODEL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_THINKING_LEVEL,
    LLM_TIMEOUT_S,
)
from app.observability import trace

# Output steps of the Interactions API that must go back to the model in the next call of the same
# tool loop. "thought" carries the thought signature that Gemini 3 requires next to each function_call.
_REPLAY_STEP_TYPES = {"thought", "function_call", "model_output"}
_STEPS_KEY = "interaction_steps"


# ---------------------------------------------------------------------------
# HTTP client: one per process, with a log line per HTTP attempt (so hidden SDK retries show up)
# ---------------------------------------------------------------------------

def _on_request(request: httpx.Request) -> None:
    request.extensions["nexus_started"] = time.perf_counter()


def _on_response(response: httpx.Response) -> None:
    started = response.request.extensions.get("nexus_started")
    ms = (time.perf_counter() - started) * 1000 if started else None
    level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
    trace.log("gemini.http", level, status=response.status_code, ms=ms, caminho=response.request.url.path)


RETRYABLE_STATUS = [408, 500, 502, 503, 504]
_CLIENT: Any = None


def _get_client() -> Any:
    global _CLIENT
    if _CLIENT is None:
        from google import genai
        from google.genai import types

        http_client = httpx.Client(
            timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0),
            event_hooks={"request": [_on_request], "response": [_on_response]},
        )
        _CLIENT = genai.Client(
            api_key=GOOGLE_API_KEY,
            http_options=types.HttpOptions(
                timeout=int(LLM_TIMEOUT_S * 1000),
                # 429 (cota/limite de taxa) NÃO é repetido: tentar de novo em segundos não resolve e só atrasa o erro.
                # Só falhas passageiras do servidor (408 e 5xx) e de rede são repetidas.
                retry_options=types.HttpRetryOptions(attempts=LLM_MAX_RETRIES,
                                                     http_status_codes=RETRYABLE_STATUS),
                httpx_client=http_client,
            ),
        )
    return _CLIENT


# ---------------------------------------------------------------------------
# ChatGoogleInteractions – LangChain chat model for gemini-3.x+ (Interactions API)
# ---------------------------------------------------------------------------

class ChatGoogleInteractions(BaseChatModel):
    """LangChain ChatModel backed by Google's Interactions API (gemini-3.x+).

    - Stateless: every call sends the whole conversation (system + history + tool loop).
    - The output steps of each call (thought + function_call) are kept in the AIMessage and sent back
      verbatim, because Gemini 3 validates the thought signature of every function call it made.
    - No temperature: Gemini 3 does not accept sampling parameters; latency/quality is tuned with
      thinking_level.
    - Token usage goes to AIMessage.usage_metadata, so LangChain's usage callback (metrics/cost) sees it.
    """

    model_name: str = Field(..., alias="model")
    thinking_level: str | None = None
    timeout: float = 60.0
    _bound_tools: list[Any] = PrivateAttr(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ChatGoogleInteractions:
        copy = ChatGoogleInteractions(model=self.model_name, thinking_level=self.thinking_level, timeout=self.timeout)
        copy._bound_tools = list(tools)
        return copy

    # --- request ---------------------------------------------------------

    @staticmethod
    def _to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        return str(content)

    def _messages_to_steps(self, messages: list[BaseMessage]) -> tuple[str, list]:
        """Return (system_instruction, input steps)."""
        system = ""
        steps: list = []
        call_names: dict[str, str] = {}
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system = self._to_text(msg.content)
            elif isinstance(msg, HumanMessage):
                steps.append({"type": "user_input", "content": [{"type": "text", "text": self._to_text(msg.content)}]})
            elif isinstance(msg, AIMessage):
                for tc in msg.tool_calls:
                    call_names[tc.get("id") or ""] = tc["name"]
                raw = msg.additional_kwargs.get(_STEPS_KEY)
                if raw:  # produced by this class: replay exactly what the model returned
                    steps.extend(raw)
                    continue
                for tc in msg.tool_calls:
                    steps.append({"type": "function_call", "id": tc.get("id") or str(uuid.uuid4()),
                                  "name": tc["name"], "arguments": tc.get("args", {})})
                text = self._to_text(msg.content)
                if text and not msg.tool_calls:  # session memory: previous answers of the assistant
                    steps.append({"type": "model_output", "content": [{"type": "text", "text": text}]})
            elif isinstance(msg, ToolMessage):
                step: dict = {"type": "function_result", "call_id": msg.tool_call_id,
                              "result": self._to_text(msg.content)}
                name = msg.name or call_names.get(msg.tool_call_id, "")
                if name:
                    step["name"] = name
                steps.append(step)
        return system, steps

    def _format_tools(self, tools: list[Any]) -> list:
        result = []
        for tool in tools:
            if not (hasattr(tool, "name") and hasattr(tool, "description")):
                continue
            params: dict = {"type": "object", "properties": {}}
            schema = getattr(tool, "tool_call_schema", None) or getattr(tool, "args_schema", None)
            if isinstance(schema, dict):
                params = schema
            elif schema is not None and hasattr(schema, "model_json_schema"):
                params = schema.model_json_schema()
            params = {k: v for k, v in params.items() if k not in ("title", "$schema", "description")}
            for prop in params.get("properties", {}).values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
            result.append({"type": "function", "name": tool.name, "description": tool.description or "",
                           "parameters": params})
        return result

    # --- call --------------------------------------------------------------

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, steps = self._messages_to_steps(messages)
        tools = list(self._bound_tools) + list(kwargs.pop("tools", None) or [])
        request: dict = {"model": self.model_name, "input": steps or ""}
        if system:
            request["system_instruction"] = system
        if self.thinking_level:
            request["generation_config"] = {"thinking_level": self.thinking_level}
        if tools:
            request["tools"] = self._format_tools(tools)

        input_chars = len(system) + sum(len(str(s)) for s in steps)
        with trace.step("gemini.chamada", service="gemini", modelo=self.model_name,
                        raciocinio=self.thinking_level or "padrão", passos_entrada=len(steps),
                        chars_entrada=input_chars, tools=len(tools)) as info:
            response = _get_client().interactions.create(**request, timeout=self.timeout)
            usage = response.usage
            tokens_in = (usage.total_input_tokens or 0) if usage else 0
            tokens_out = (usage.total_output_tokens or 0) if usage else 0
            tokens_thought = (usage.total_thought_tokens or 0) if usage else 0
            out_steps = [s.model_dump(mode="json", by_alias=True, exclude_none=True) for s in (response.steps or [])]
            tool_calls = [
                {"id": s.get("id") or str(uuid.uuid4()), "name": s["name"], "args": s.get("arguments") or {},
                 "type": "tool_call"}
                for s in out_steps if s.get("type") == "function_call"
            ]
            text = response.output_text or ""
            info.update(status=getattr(response, "status", None), tokens_in=tokens_in, tokens_out=tokens_out,
                        tokens_raciocinio=tokens_thought,
                        tool_calls=",".join(c["name"] for c in tool_calls) or None, chars_resposta=len(text))

        message = AIMessage(
            content=text,
            tool_calls=tool_calls,
            additional_kwargs={_STEPS_KEY: [s for s in out_steps if s.get("type") in _REPLAY_STEP_TYPES]},
            response_metadata={"model_name": self.model_name},
            usage_metadata={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out + tokens_thought,  # thinking is billed as output
                "total_tokens": tokens_in + tokens_out + tokens_thought,
                "output_token_details": {"reasoning": tokens_thought},
            },
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "google-interactions"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def uses_interactions_api(model: str) -> bool:
    """gemini-3.x and newer go through the Interactions API."""
    import re

    m = re.match(r"gemini-(\d+)", model)
    return bool(m and int(m.group(1)) >= 3)


def get_llm(model: str | None = None) -> BaseChatModel:
    model = model or LLM_MODEL
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY não definida. Preencha o arquivo .env (veja .env.example).")
    if uses_interactions_api(model):
        return ChatGoogleInteractions(model=model, thinking_level=LLM_THINKING_LEVEL or None,
                                      timeout=LLM_TIMEOUT_S)

    # gemini-2.x (generateContent through langchain-google-genai)
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=model, temperature=LLM_TEMPERATURE, google_api_key=GOOGLE_API_KEY,
                                  max_retries=LLM_MAX_RETRIES, timeout=LLM_TIMEOUT_S)


def get_fallback_llm() -> BaseChatModel | None:
    """Reserva usada quando o modelo principal falha; None se desligada ou igual ao principal."""
    if not LLM_FALLBACK_MODEL or LLM_FALLBACK_MODEL == LLM_MODEL:
        return None
    return get_llm(LLM_FALLBACK_MODEL)


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
    """Translate the most common Gemini API errors into a readable message (never with credentials)."""
    msg = trace.redact(error)
    if is_quota_error(error):
        return f"Gemini: limite/cota atingido para o modelo '{LLM_MODEL}'. Detalhe: {msg}"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)) or "504" in msg or "DEADLINE_EXCEEDED" in msg:
        return f"Gemini: tempo limite excedido ({LLM_TIMEOUT_S:.0f}s por chamada). Detalhe: {msg}"
    if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
        return f"Gemini: modelo '{LLM_MODEL}' sobrecarregado. Tente de novo. Detalhe: {msg}"
    if "API_KEY_INVALID" in msg or "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
        return f"Gemini: chave de API inválida ou sem permissão. Detalhe: {msg}"
    if "404" in msg or "NOT_FOUND" in msg:
        return f"Gemini: modelo '{LLM_MODEL}' não encontrado para esta chave. Detalhe: {msg}"
    if isinstance(error, httpx.TransportError):
        return f"Gemini: falha de rede ao chamar a API. Detalhe: {msg}"
    return f"Gemini: {type(error).__name__}: {msg}"


if __name__ == "__main__":
    trace.configure_logging()
    trace.start_request()
    print(f"Modelo: {LLM_MODEL} | API: {'Interactions' if uses_interactions_api(LLM_MODEL) else 'generateContent'}"
          f" | raciocínio: {LLM_THINKING_LEVEL} | timeout: {LLM_TIMEOUT_S}s | retries do SDK: {LLM_MAX_RETRIES}")
    try:
        for attempt in (1, 2):
            started = time.perf_counter()
            answer = get_llm().invoke("Responda apenas: ok").content
            print(f"Chamada {attempt}: {(time.perf_counter() - started):.2f}s -> {answer!r}")
    except Exception as error:  # noqa: BLE001
        print("FALHOU ->", explain_error(error))
