"""Admin panel: the aggregations of the BI IA page and the routes that serve them.

MongoDB and LangSmith are replaced by doubles: what is tested is the arithmetic and the JSON shape the
panel reads. Run from the project root: python -m pytest -q tests
"""
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app import app
from app.auth import admin_key
from app.auth.admin_key import verify_admin_key
from app.services import admin_service, langsmith_service

END = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


def doc(route="analyst", ms=2000.0, hours_ago=1, **extra):
    base = {
        "trace_id": f"t-{route}-{ms}-{hours_ago}",
        "created_at": (END - timedelta(hours=hours_ago)).replace(tzinfo=None),
        "route": route,
        "resolved": route in admin_service.SPECIALIST_ROUTES,
        "blocked": route == "blocked",
        "attempts": 1 if route in admin_service.SPECIALIST_ROUTES else 0,
        "error": False,
        "latency_total_ms": ms,
        "latency_by_node_ms": {},
        "input_tokens": 100,
        "output_tokens": 40,
        "cost_usd": 0.002,
        "model": "gemini-2.5-flash",
    }
    base.update(extra)
    return base


class TestJudgeDecisions(unittest.TestCase):
    def test_rebuilt_from_attempts_and_final_verdict(self):
        self.assertEqual(admin_service.judge_decisions(doc(attempts=1)), ["aprovado"])
        self.assertEqual(admin_service.judge_decisions(doc(attempts=2)), ["devolvido", "aprovado"])
        self.assertEqual(
            admin_service.judge_decisions(doc(attempts=2, resolved=False)), ["devolvido", "devolvido"]
        )

    def test_questions_that_never_reach_the_judge(self):
        self.assertEqual(admin_service.judge_decisions(doc(route="out_of_scope")), [])
        self.assertEqual(admin_service.judge_decisions(doc(route="blocked")), [])


class TestDashboardSections(unittest.TestCase):
    def test_summary(self):
        docs = [doc(), doc(attempts=2), doc(route="faq", ms=800), doc(error=True, resolved=False, attempts=0)]

        numbers = admin_service.summary(docs)

        self.assertEqual(numbers["execucoes"], 4)
        self.assertEqual(numbers["taxa_erro_pct"], 25.0)
        self.assertEqual(numbers["devolucoes_juiz_pct"], 25.0)
        self.assertEqual(numbers["custo_usd"], 0.008)

    def test_latency_by_stage_groups_the_nodes(self):
        docs = [
            doc(latency_by_node_ms={"router": 1000, "specialist": 4000, "judge": 500,
                                    "input_guardrail": 10, "finish": 90}),
            doc(latency_by_node_ms={"router": 3000, "specialist": 2000, "judge": 1500,
                                    "input_guardrail": 10, "finish": 90}),
        ]

        [row] = admin_service.latency_by_stage(docs)

        self.assertEqual(row["etapas_s"]["roteador"], 2.0)
        self.assertEqual(row["etapas_s"]["agente"], 3.0)
        self.assertEqual(row["etapas_s"]["juiz"], 1.0)
        self.assertEqual(row["etapas_s"]["guardrails"], 0.1)
        self.assertEqual(row["etapas_s"]["orquestrador"], 0.0)

    def test_tokens_without_daily_limit(self):
        tokens = admin_service.tokens_by_day([doc(), doc(hours_ago=30)], END - timedelta(days=2), END)

        self.assertEqual(len(tokens["dias"]), 3)
        self.assertEqual(tokens["total_entrada"], 200)
        self.assertIsNone(tokens["limite_diario"])
        self.assertIsNone(tokens["pico"]["pct_do_limite"])

    def test_quota_errors_by_hour(self):
        docs = [
            doc(error=True, quota_error=True),
            doc(error=True, error_type="ResourceExhausted", hours_ago=2),
            doc(error=True, error_type="ValueError"),
            doc(error=True, quota_error=True, hours_ago=40),
        ]

        quota = admin_service.quota_errors(docs, END)

        self.assertEqual(quota["total_24h"], 2)
        self.assertEqual(quota["total_janela"], 3)

    def test_guardrails_input_and_output(self):
        blocks = admin_service.guardrails([doc(route="blocked"), doc(output_blocked=True), doc(), doc()])

        self.assertEqual(blocks["entrada"], 1)
        self.assertEqual(blocks["saida"], 1)
        self.assertEqual(blocks["pct"], 50.0)

    def test_dashboard_with_empty_database(self):
        with patch.object(admin_service, "find_metrics_between", return_value=[]), \
             patch.object(admin_service, "find_tool_calls_between", return_value=[]):
            page = admin_service.build_dashboard(7, END)

        self.assertEqual(page["resumo"]["execucoes"], 0)
        self.assertIsNone(page["leitura_nota"])
        self.assertEqual(page["qualidade"]["juiz"]["revertido"]["quantidade"], 0)


class TestPeriodReport(unittest.TestCase):
    def test_compares_with_the_previous_period(self):
        current = [doc(), doc(), doc(error=True, resolved=False)]
        previous = [doc(hours_ago=200), doc(hours_ago=200)]

        with patch.object(admin_service, "find_metrics_between",
                          side_effect=lambda since, until: current if until == END else previous), \
             patch.object(admin_service, "find_tool_calls_between", return_value=[
                 {"tool_name": "search_reports_by_period", "duration_ms": 10, "success": False},
                 {"tool_name": "search_faq", "duration_ms": 10, "success": True},
             ]):
            report = admin_service.build_period_report(7, END)

        indicators = {row["indicador"]: row for row in report["indicadores"]}
        self.assertEqual(indicators["volume"]["variacao"], 50.0)
        self.assertEqual(indicators["taxa_erro_pct"]["variacao"], 33.33)
        self.assertEqual([t["tool"] for t in report["tools_com_mais_erro"]], ["search_reports_by_period"])


class TestLangSmith(unittest.TestCase):
    def test_per_day_chain_latency_and_feedback(self):
        start = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
        roots = [
            SimpleNamespace(name="orchestrator", status="success", start_time=start,
                            end_time=start + timedelta(seconds=3), feedback_stats={"nota": {"n": 2, "avg": 0.5}}),
            SimpleNamespace(name="orchestrator", status="error", start_time=start,
                            end_time=start + timedelta(seconds=1), feedback_stats=None),
        ]
        chains = [
            SimpleNamespace(name="judge", start_time=start, end_time=start + timedelta(seconds=1)),
            SimpleNamespace(name="judge", start_time=start, end_time=start + timedelta(seconds=3)),
        ]

        days = langsmith_service.runs_per_day(roots)
        latency = langsmith_service.latency_by_name(chains, langsmith_service.CHAIN_RUNS)
        feedback = langsmith_service.feedback(roots)

        self.assertEqual(days, [{"dia": "2026-10-20", "execucoes": 2, "erros": 1, "taxa_erro_pct": 50.0}])
        self.assertEqual(latency[0]["p99_s"], 3.0)
        self.assertEqual(feedback["total"], 2)
        self.assertEqual(feedback["por_chave"]["nota"]["media"], 0.5)

    def test_langsmith_down_does_not_break_the_panel(self):
        with patch.object(langsmith_service, "find_metrics_between", return_value=[]), \
             patch.object(langsmith_service, "Client", side_effect=RuntimeError("sem chave")):
            section = langsmith_service.build_langsmith(7)

        self.assertFalse(section["disponivel"])


class TestAdminRoutes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_admin_key_is_required(self):
        with patch.object(admin_key, "ADMIN_API_KEY", "chave-certa"):
            self.assertEqual(self.client.get("/admin/session").status_code, 401)
            wrong = self.client.get("/admin/session", headers={"X-Admin-Key": "outra"})
            right = self.client.get("/admin/session", headers={"X-Admin-Key": "chave-certa"})

        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(right.status_code, 200)
        self.assertEqual(right.json()["servico"], "ceris-bi-ia")

    def test_app_api_key_does_not_open_the_panel(self):
        with patch.object(admin_key, "ADMIN_API_KEY", "chave-certa"):
            response = self.client.get("/admin/metrics", headers={"X-API-Key": "chave-certa"})

        self.assertEqual(response.status_code, 401)

    def test_no_key_configured_is_503(self):
        with patch.object(admin_key, "ADMIN_API_KEY", ""):
            response = self.client.get("/admin/session", headers={"X-Admin-Key": "qualquer"})

        self.assertEqual(response.status_code, 503)

    def test_metrics_route_passes_the_window(self):
        app.dependency_overrides[verify_admin_key] = lambda: None
        self.addCleanup(app.dependency_overrides.clear)

        with patch.object(admin_service, "build_dashboard", return_value={"resumo": {}}) as build:
            response = self.client.get("/admin/metrics?dias=14")

        self.assertEqual(response.status_code, 200)
        build.assert_called_once_with(14)
        self.assertEqual(self.client.get("/admin/metrics?dias=0").status_code, 422)

    def test_old_metrics_route_moved_to_admin(self):
        self.assertEqual(self.client.get("/metrics/report").status_code, 404)


if __name__ == "__main__":
    unittest.main()
