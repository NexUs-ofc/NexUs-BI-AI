"""Compatibilidade: o gerador de relatórios não é mais uma API separada.

As rotas que estavam aqui (/dashboard e /reports/...) agora são servidas pela API única do projeto,
app/app.py, a partir de app/controller/report_controller.py. Este módulo só reexporta aquele app, para que
`uvicorn report_generator.api:app` (comando antigo) suba a MESMA aplicação, e não uma segunda.

    python -m uvicorn app.app:app --reload   ->  http://localhost:8000/docs
"""
from app.app import app

__all__ = ["app"]
