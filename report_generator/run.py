"""Linha de comando do gerador (rode na raiz do projeto).

    python -m report_generator.run 2026 10                 # gera outubro/2026 (agentes de IA + PDF)
    python -m report_generator.run 2026 10 --sem-pdf       # só o JSON no Mongo
    python -m report_generator.run 2026 10 --historico 6   # gera antes os 6 meses anteriores (sem IA e
                                                           # sem PDF) para o Mongo ter histórico (mock)
    python -m report_generator.run --mes-anterior          # o mês que acabou, igual ao agendador: não refaz se já
                                                           # existir (use em cron externo; --forcar refaz)
    python -m report_generator.run --diario                # o que o agendador diário faz: atualiza o mês atual
                                                           # (parcial) e fecha o anterior se ainda não fechou
    python -m report_generator.run --atualizar-pdfs        # refaz os PDFs de todos os relatórios do Mongo com o
                                                           # template atual (sem chamar a IA)
    python -m report_generator.run 2026 9 --historico 6 --atualizar-pdfs   # cria os 6 meses anteriores que
                                                           # faltam e refaz todos os PDFs (sem IA)
"""
import argparse
import logging
import sys

from report_generator import pipeline
from report_generator.config import validate_config
from report_generator.scheduler import generate_daily, generate_previous_month
from report_generator.storage import files, mongo


def _previous_months(ano: int, mes: int, n: int) -> list[tuple[int, int]]:
    out = []
    for _ in range(n):
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
        out.append((ano, mes))
    return out[::-1]


def update_pdfs() -> int:
    """Gera de novo o PDF de cada relatório do Mongo a partir do JSON salvo. Não muda dados, narrativa nem status."""
    done = 0
    for item in reversed(mongo.list_reports()):  # do mais antigo para o mais novo
        ano, mes = item["ano"], item["mes"]
        report = mongo.find_report(ano, mes)
        if not report or "dados" not in report or "narrativa" not in report:
            print(f"  {mes:02d}/{ano}: ignorado (documento sem dados/narrativa)")
            continue
        uri = files.save_pdf(pipeline.render_pdf(report), ano, mes)
        mongo.set_pdf(ano, mes, uri)
        done += 1
        print(f"  {mes:02d}/{ano}: PDF atualizado -> {uri}")
    print(f"\n{done} PDF(s) atualizados.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o relatório mensal do NexUs BI.")
    parser.add_argument("ano", type=int, nargs="?")
    parser.add_argument("mes", type=int, nargs="?")
    parser.add_argument("--mes-anterior", action="store_true",
                        help="gera o mês que acabou, como o agendador (não refaz se já existir; ignora ano/mes)")
    parser.add_argument("--diario", action="store_true",
                        help="roda o disparo diário do agendador (mês atual parcial + fecha o anterior); para cron externo")
    parser.add_argument("--forcar", action="store_true", help="com --mes-anterior: gera de novo mesmo se já existir")
    parser.add_argument("--atualizar-pdfs", action="store_true",
                        help="refaz os PDFs de todos os relatórios já salvos, sem IA (template e gráficos atuais)")
    parser.add_argument("--sem-pdf", action="store_true", help="não gera o PDF")
    parser.add_argument("--historico", type=int, default=0, help="gera antes N meses anteriores (sem IA/PDF)")
    args = parser.parse_args(argv)
    if args.atualizar_pdfs:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        # Com ano, mes e --historico N: antes cria os N meses anteriores que faltam (só números, sem IA)
        if args.historico and args.ano and args.mes:
            for a, m in _previous_months(args.ano, args.mes, args.historico):
                if not mongo.find_report(a, m):
                    pipeline.run(a, m, use_ai=False, with_pdf=False)
                    print(f"  {m:02d}/{a}: histórico criado")
        return update_pdfs()
    if not args.mes_anterior and not args.diario and (args.ano is None or args.mes is None):
        parser.error("informe ano e mês (ex.: 2026 10) ou use --mes-anterior / --diario")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    problems = validate_config(use_ai=True)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    if args.diario:
        result = generate_daily()
        print(result)
        failed = [a for a in result["acoes"] if (mongo.find_job(a["ano"], a["mes"]) or {}).get("status") == "erro"]
        return 1 if failed else 0

    if args.mes_anterior:
        result = generate_previous_month(force=args.forcar)
        print(result)
        job = mongo.find_job(result["ano"], result["mes"]) or {}
        return 1 if job.get("status") == "erro" and result["acao"] == "gerado" else 0

    for a, m in _previous_months(args.ano, args.mes, args.historico):
        pipeline.run(a, m, use_ai=False, with_pdf=False)

    report = pipeline.run(args.ano, args.mes, use_ai=True, with_pdf=not args.sem_pdf)

    print(f"\nRelatório {args.mes:02d}/{args.ano} gerado e publicado.")
    for code, k in report["dados"]["kpis"].items():
        print(f"  {code} {k['nome']}: {k['valor']}{k['unidade']} [{k['status']}]")
    if report["qualidade"]["numeros_sem_fonte"]:
        print(f"  Atenção, números sem fonte na narrativa: {report['qualidade']['numeros_sem_fonte']}")
    if report.get("pdf"):
        print(f"  PDF: {report['pdf']['uri']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
