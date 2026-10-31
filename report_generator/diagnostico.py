"""Diagnóstico: o que o gerador enxerga no MongoDB, no Supabase Storage e no Databricks.

    python -m report_generator.diagnostico                # só LÊ (Mongo, Supabase, Databricks: 1 consulta leve)
    python -m report_generator.diagnostico --escrever     # também testa gravar no Mongo e no bucket (apaga o teste)
    python -m report_generator.diagnostico --sem-databricks   # pula o Databricks (poupa a cota)

Mostra, por exemplo, por que a coleção `reports` está vazia: o `erro` do último job aparece na seção Mongo.
"""
import argparse
import sys
from datetime import UTC, datetime

from report_generator import config
from report_generator.storage import files, mongo

# Coleções que ESTE projeto usa (gerador + chatbot). Qualquer outra do banco não é lida nem escrita pelo código.
CONHECIDAS = {
    config.MONGODB_REPORTS_COLLECTION: "relatórios (gerador grava, chatbot lê)",
    config.MONGODB_JOBS_COLLECTION: "andamento da geração (gerador)",
    "metrics_bi": "métricas do chatbot (app/)",
    "tool_metrics_bi": "métricas de tools do chatbot (app/)",
}


def _ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [!]    {msg}")


def _fail(msg: str) -> None:
    print(f"  [ERRO] {msg}")


def check_mongo(escrever: bool) -> bool:
    print(f"\nMongoDB  (banco '{config.MONGODB_DB}')")
    try:
        db = mongo.get_db()
        db.command("ping")
        _ok("conectou")
        nomes = sorted(db.list_collection_names())
    except Exception as error:  # noqa: BLE001
        _fail(f"{type(error).__name__}: {error}")
        return False
    for nome in nomes:
        total = db[nome].estimated_document_count()
        if nome in CONHECIDAS:
            _ok(f"{nome}: {total} documento(s) - {CONHECIDAS[nome]}")
        else:
            _warn(f"{nome}: {total} documento(s) - NÃO é usada por este código (pode apagar se for sobra de teste)")
    for nome in CONHECIDAS:
        if nome not in nomes:
            _warn(f"{nome}: ainda não existe (é criada na primeira gravação)")

    reports = mongo.list_reports() if config.MONGODB_REPORTS_COLLECTION in nomes else []
    print(f"\n  Relatórios em '{config.MONGODB_REPORTS_COLLECTION}': {len(reports)}")
    for r in reports:
        pdf = "com PDF" if r.get("pdf") else "sem PDF"
        parcial = " (parcial)" if r.get("parcial") else ""
        print(f"    {r['mes']:02d}/{r['ano']}  {r.get('status', '?'):<10} {pdf}{parcial}  gerado em {r.get('gerado_em')}")
    jobs = list(db[config.MONGODB_JOBS_COLLECTION].find({}, {"_id": 0}).sort("atualizado_em", -1)) \
        if config.MONGODB_JOBS_COLLECTION in nomes else []
    print(f"\n  Jobs em '{config.MONGODB_JOBS_COLLECTION}': {len(jobs)} (1 por mês; guarda as últimas execuções)")
    for j in jobs:
        print(f"    {j['mes']:02d}/{j['ano']}  {j['status']:<12} atualizado em {j.get('atualizado_em')}")
        if j.get("erro"):
            _fail(f"último erro: {j['erro']}")
        for h in (j.get("historico") or [])[-5:]:
            print(f"        - {h.get('em')}  {h.get('status')}" + (f"  {h['erro']}" if h.get("erro") else ""))

    if escrever:
        teste = db["_diagnostico_tmp"]
        try:
            teste.replace_one({"_id": "ping"}, {"_id": "ping", "em": datetime.now(UTC)}, upsert=True)
            ok = teste.find_one({"_id": "ping"}) is not None
            teste.drop()
            (_ok if ok else _fail)("gravar e ler de volta no Mongo")
        except Exception as error:  # noqa: BLE001
            _fail(f"gravação falhou: {type(error).__name__}: {error}")
            return False
    return True


def check_supabase(escrever: bool) -> bool:
    print(f"\nSupabase Storage  (bucket '{config.SUPABASE_BUCKET}', pasta '{config.SUPABASE_PREFIX}')")
    if not config.SUPABASE_URL:
        _warn("SUPABASE_URL vazio: os PDFs ficam na pasta local " + str(config.OUTPUT_DIR))
        return True
    import httpx

    kind = "sb_secret (só no header apikey)" if config.SUPABASE_KEY.startswith("sb_") else "JWT service_role"
    _ok(f"chave do tipo {kind}")
    try:
        r = httpx.get(f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/bucket/{config.SUPABASE_BUCKET}",
                      headers=files._headers(), timeout=files.TIMEOUT)
        if r.is_error:
            _fail(f"bucket '{config.SUPABASE_BUCKET}': {r.status_code} {r.text[:200]}")
            return False
        _ok("bucket encontrado" + (" (PRIVADO)" if not r.json().get("public") else " (público: prefira privado)"))
        if escrever:
            name = f"{config.SUPABASE_PREFIX.strip('/')}/_diagnostico.txt"
            up = httpx.post(files._object_url(config.SUPABASE_BUCKET, name), content=b"ok",
                            headers=files._headers(**{"Content-Type": "text/plain", "x-upsert": "true"}),
                            timeout=files.TIMEOUT)
            if up.is_error:
                _fail(f"upload de teste: {up.status_code} {up.text[:200]}")
                return False
            _ok("upload de teste")
            httpx.delete(files._object_url(config.SUPABASE_BUCKET, name), headers=files._headers(),
                         timeout=files.TIMEOUT)
    except Exception as error:  # noqa: BLE001
        _fail(f"{type(error).__name__}: {error}")
        return False
    return True


def check_databricks() -> bool:
    print(f"\nDatabricks  ({config.DATABRICKS['catalog']}.{config.DATABRICKS['schema']}, fonte = {config.DATA_SOURCE})")
    if config.DATA_SOURCE not in ("databricks", "db"):
        _warn("REPORT_DATA_SOURCE não é 'databricks': os relatórios usam dados fictícios (mock)")
        return True
    try:
        from report_generator.data.databricks import _connect, table_name

        with _connect() as connection, connection.cursor() as cursor:
            # 1 consulta leve, só nas tabelas kpi_*
            cursor.execute(f"SELECT (SELECT MAX(`ano_mes`) FROM {table_name('kpi_desperdicio_mensal')}) AS ultimo_mes_evento, "
                           f"(SELECT MIN(`data_referencia`) FROM {table_name('kpi_estado_diario')}) AS primeira_foto, "
                           f"(SELECT MAX(`data_referencia`) FROM {table_name('kpi_estado_diario')}) AS ultima_foto")
            row = cursor.fetchone()
        _ok(f"conectou. Eventos até {row[0]}; fotos da despensa de {row[1]} a {row[2]}")
    except Exception as error:  # noqa: BLE001
        _fail(f"{type(error).__name__}: {error}")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico do gerador de relatórios do NexUs BI.")
    parser.add_argument("--escrever", action="store_true", help="testa gravar no Mongo e no bucket (e apaga o teste)")
    parser.add_argument("--sem-databricks", action="store_true", help="não consulta o Databricks")
    args = parser.parse_args(argv)
    results = [check_mongo(args.escrever), check_supabase(args.escrever)]
    if not args.sem_databricks:
        results.append(check_databricks())
    print()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
