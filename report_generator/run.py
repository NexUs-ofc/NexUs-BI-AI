"""Linha de comando do gerador (rode na raiz do projeto).

    python -m report_generator.run 2026 10                 # gera outubro/2026 (agentes + PDF)
    python -m report_generator.run 2026 10 --sem-ia        # narrativa por regras, sem Gemini
    python -m report_generator.run 2026 10 --sem-pdf       # só o JSON no Mongo
    python -m report_generator.run 2026 10 --historico 6   # gera antes os 6 meses anteriores (sem IA e
                                                           # sem PDF) para o Mongo ter histórico (mock)
    python -m report_generator.run 2026 10 --publicar      # marca como publicado (o chatbot passa a ver)
"""
import argparse
import logging
import sys

from report_generator import pipeline
from report_generator.config import validate_config
from report_generator.storage import mongo


def _previous_months(ano: int, mes: int, n: int) -> list[tuple[int, int]]:
    out = []
    for _ in range(n):
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
        out.append((ano, mes))
    return out[::-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o relatório mensal do NexUs BI.")
    parser.add_argument("ano", type=int)
    parser.add_argument("mes", type=int)
    parser.add_argument("--sem-ia", action="store_true", help="narrativa por regras, sem chamar o Gemini")
    parser.add_argument("--sem-pdf", action="store_true", help="não gera o PDF")
    parser.add_argument("--historico", type=int, default=0, help="gera antes N meses anteriores (sem IA/PDF)")
    parser.add_argument("--publicar", action="store_true", help="marca o relatório como publicado")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    problems = validate_config(use_ai=not args.sem_ia)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    for a, m in _previous_months(args.ano, args.mes, args.historico):
        pipeline.run(a, m, use_ai=False, with_pdf=False)
        mongo.set_status(a, m, "publicado")

    report = pipeline.run(args.ano, args.mes, use_ai=not args.sem_ia, with_pdf=not args.sem_pdf)
    if args.publicar:
        mongo.set_status(args.ano, args.mes, "publicado")

    print(f"\nRelatório {args.mes:02d}/{args.ano} gerado ({'publicado' if args.publicar else 'rascunho'}).")
    for code, k in report["dados"]["kpis"].items():
        print(f"  {code} {k['nome']}: {k['valor']}{k['unidade']} [{k['status']}]")
    if report["qualidade"]["numeros_sem_fonte"]:
        print(f"  Atenção, números sem fonte na narrativa: {report['qualidade']['numeros_sem_fonte']}")
    if report.get("pdf"):
        print(f"  PDF: {report['pdf']['uri']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
