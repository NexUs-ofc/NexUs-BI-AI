"""CLI do assistente multiagente NexUs BI.

Rodar a partir da raiz do projeto:
    python -m app.app            # modo normal
    python -m app.app --debug    # mostra rota, veredito do juiz e guardrails

Comandos: 'exit' ou 'sair' encerram | 'limpar' apaga a memória da sessão.
"""
import sys
import uuid

from app.controller.orquestrador import Orquestrador
from app.core.memory import limpar_sessao

SAIR = {"exit", "sair", "quit"}


def main() -> None:
    debug = "--debug" in sys.argv
    session_id = str(uuid.uuid4())  # memória vale só para esta execução
    orq = Orquestrador(session_id)

    print("NexUs BI - assistente multiagente. Digite 'exit' para sair.\n")
    while True:
        try:
            mensagem = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not mensagem:
            continue
        if mensagem.lower() in SAIR:
            break
        if mensagem.lower() == "limpar":
            limpar_sessao(session_id)
            print("Memória da sessão apagada.\n")
            continue

        try:
            resultado = orq.processar(mensagem)
        except Exception as e:  # noqa: BLE001
            print(f"[erro] {e}\n")
            continue

        if debug:
            for passo in resultado.passos:
                print(f"  · {passo}")
        print(f"- {resultado.resposta}\n")

    limpar_sessao(session_id)
    print("Encerrando a conversa.")


if __name__ == "__main__":
    main()
