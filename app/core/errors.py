"""Erros que o chat devolve ao usuário com uma mensagem clara (em vez de seguir com dado falso)."""


class ExternalServiceError(Exception):
    """Um serviço externo do chat falhou ou está mal configurado (MongoDB, Qdrant...).

    O chat para e responde 503 com `message`: nunca continua com um dado inventado ou de mentira.
    """

    def __init__(self, service: str, message: str) -> None:
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message
