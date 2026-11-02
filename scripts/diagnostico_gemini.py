"""Descobre ONDE o Gemini demora, sem passar pelo chat. Uso (na pasta do back):

    python -m scripts.diagnostico_gemini

Cada teste tem limite de 25 s e mostra o tempo. Não imprime a chave nem o conteúdo das respostas.
  1. rede: DNS, conexão TCP e TLS até generativelanguage.googleapis.com, e se há proxy configurado
  2. generateContent com o modelo do .env e com gemini-3.5-flash-lite (o que o NexUs-AI usa como reserva)
  3. Interactions API com o modelo do .env (o que o chat usa hoje)
"""
import os
import socket
import ssl
import time

from app.config import GOOGLE_API_KEY, LLM_MODEL

HOST = "generativelanguage.googleapis.com"
LIMITE_S = 25


def medir(nome, funcao):
    inicio = time.perf_counter()
    try:
        resultado = funcao()
        print(f"  OK    {time.perf_counter() - inicio:6.2f}s  {nome}  {resultado or ''}")
    except Exception as erro:  # noqa: BLE001
        texto = str(erro).replace(GOOGLE_API_KEY, "***") if GOOGLE_API_KEY else str(erro)
        print(f"  FALHA {time.perf_counter() - inicio:6.2f}s  {nome}  {type(erro).__name__}: {texto[:160]}")


def rede():
    print("1) Rede")
    proxies = {k: bool(v) for k, v in os.environ.items() if k.upper() in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")}
    print(f"  proxy no ambiente: {proxies or 'nenhum'}")
    medir("DNS", lambda: socket.gethostbyname(HOST))
    medir("TCP 443", lambda: socket.create_connection((HOST, 443), timeout=10).close())

    def tls():
        with socket.create_connection((HOST, 443), timeout=10) as sock, \
                ssl.create_default_context().wrap_socket(sock, server_hostname=HOST) as secure:
            return secure.version()

    medir("TLS", tls)


def gemini():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GOOGLE_API_KEY, http_options=types.HttpOptions(
        timeout=LIMITE_S * 1000, retry_options=types.HttpRetryOptions(attempts=1)))
    print(f"\n2) generateContent (SDK google-genai {genai.__version__ if hasattr(genai, '__version__') else '?'})")
    for modelo in dict.fromkeys([LLM_MODEL, "gemini-3.5-flash-lite"]):
        medir(modelo, lambda m=modelo: client.models.generate_content(
            model=m, contents="Responda apenas: ok").text)
    print("\n3) Interactions API")
    medir(LLM_MODEL, lambda: client.interactions.create(
        model=LLM_MODEL, input="Responda apenas: ok", generation_config={"thinking_level": "low"},
        timeout=LIMITE_S).steps[-1].type)


if __name__ == "__main__":
    if not GOOGLE_API_KEY:
        raise SystemExit("GOOGLE_API_KEY não definida no .env")
    rede()
    gemini()
