"""Fábrica da LLM. Para trocar de provedor, altere só este arquivo.

Diagnóstico rápido da chave/modelo (rodar na raiz do projeto):
    python -m app.model.llm
"""
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import GOOGLE_API_KEY, LLM_MODEL, LLM_TEMPERATURE


def get_llm(temperature: float | None = None) -> ChatGoogleGenerativeAI:
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY não definida. Preencha o arquivo .env (veja .env.example).")
    return ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE if temperature is None else temperature,
        google_api_key=GOOGLE_API_KEY,
        max_retries=1,   # falha rápido em vez de ficar tentando de novo (429/503)
        timeout=60,
    )


def explicar_erro(e: Exception) -> str:
    """Traduz os erros mais comuns da API do Gemini."""
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        return f"Limite/cota da API atingido para o modelo '{LLM_MODEL}'. Espere um pouco ou troque LLM_MODEL no .env. Detalhe: {msg[:300]}"
    if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
        return f"Modelo '{LLM_MODEL}' sobrecarregado no momento. Tente de novo ou troque LLM_MODEL no .env. Detalhe: {msg[:300]}"
    if "API_KEY_INVALID" in msg or "401" in msg or "403" in msg or "PERMISSION_DENIED" in msg:
        return f"Chave de API inválida ou sem permissão para a Gemini API. Detalhe: {msg[:300]}"
    if "404" in msg or "NOT_FOUND" in msg:
        return f"Modelo '{LLM_MODEL}' não encontrado para esta chave. Troque LLM_MODEL no .env. Detalhe: {msg[:300]}"
    return f"{type(e).__name__}: {msg[:500]}"


if __name__ == "__main__":
    print(f"Testando modelo '{LLM_MODEL}' (chave começa com '{GOOGLE_API_KEY[:6]}...')")
    try:
        print("OK ->", get_llm().invoke("Responda apenas: ok").content)
    except Exception as erro:  # noqa: BLE001
        print("FALHOU ->", explicar_erro(erro))
