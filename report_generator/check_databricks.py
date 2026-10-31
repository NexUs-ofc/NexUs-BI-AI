"""Testa a conexão com a Gold do Databricks usando o .env da raiz do projeto.

Não escreve em lugar nenhum (Mongo, Supabase etc.) — só conecta, roda as 10 consultas (kpi_* + fato_*
agregadas) do mês fechado mais recente e mostra quantas linhas cada uma trouxe.

    python report_generator/check_databricks.py             # mês fechado mais recente
    python report_generator/check_databricks.py 2026 9       # um mês específico (ano mes)
"""
import sys

sys.path.insert(0, ".")

from report_generator.config import DATABRICKS, validate_config


def main() -> None:
    problems = validate_config()
    if problems:
        print("Configuração incompleta:", problems)
        print("Confira DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH e DATABRICKS_TOKEN no .env.")
        sys.exit(1)

    print("hostname:", DATABRICKS["server_hostname"])
    print("http_path:", DATABRICKS["http_path"])
    print("token definido:", bool(DATABRICKS["access_token"]))
    print("catalog/schema:", DATABRICKS["catalog"], "/", DATABRICKS["schema"])

    if len(sys.argv) >= 3:
        ano, mes = int(sys.argv[1]), int(sys.argv[2])
    else:
        import datetime
        hoje = datetime.date.today()
        ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)

    print(f"\nConectando e lendo a Gold de {mes:02d}/{ano}... (pode demorar uns segundos pro warehouse acordar)")
    try:
        from report_generator.data.databricks import load_gold
        gold = load_gold(ano, mes)
    except Exception as error:  # noqa: BLE001 — script de diagnóstico: qualquer falha deve virar mensagem, não traceback
        print(f"\nFALHOU: {type(error).__name__}: {error}")
        print("Confira: token não expirou, http_path é do warehouse certo, e o warehouse está disponível.")
        sys.exit(1)

    print("\nOK! Conectou e leu a Gold.")
    print("data_foto (kpi_cards):", gold.data_foto)
    print("kpi_desperdicio_mensal:", len(gold.mensal), "linhas")
    print("kpi_estado_diario:", len(gold.estado), "linhas")
    print("kpi_uf:", len(gold.uf), "linhas")
    for name, df in gold.fatos.items():
        print(f"fatos[{name}]:", len(df), "linhas")


if __name__ == "__main__":
    main()
