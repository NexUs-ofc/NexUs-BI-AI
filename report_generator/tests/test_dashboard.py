"""JSON do Dashboard: formato do front (NexUs-Web, validateDashboard.ts) e privacidade."""
from report_generator.analysis.dashboard import build_dashboard
from report_generator.data.mock import build_month

CONTRACT = {"summary", "monthlyTarget", "monthlyWaste", "stateWaste", "regions", "categories", "regionalWaste",
            "regionalConsumption", "shelfLifeDistribution", "categoryShelfLife", "belowMinimum"}


def _walk_numbers(value):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_numbers(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_numbers(v)


def test_matches_front_end_contract():
    d = build_dashboard(build_month(2026, 10))
    assert CONTRACT <= d.keys()
    contract = {k: d[k] for k in CONTRACT}
    assert None not in list(_walk_numbers(contract)) and all(n >= 0 for n in _walk_numbers(contract))
    for key in CONTRACT - {"summary", "monthlyTarget"}:
        ids = [item["id"] for item in d[key]]
        assert len(ids) == len(set(ids)), key
    category_ids = {c["id"] for c in d["categories"]}
    region_ids = {r["id"] for r in d["regions"]}
    for cell in [*d["regionalWaste"], *d["regionalConsumption"]]:
        assert cell["categoryId"] in category_ids and cell["regionId"] in region_ids
    assert {s["categoryId"] for s in d["categoryShelfLife"]} <= category_ids
    assert {s["level"] for s in d["stateWaste"]} <= {"highest", "intermediate", "average", "lowest"}
    assert 0 <= d["summary"]["wasteRate"] <= 100 and d["monthlyTarget"] == 15.0
    assert [b["label"] for b in d["shelfLifeDistribution"]][-1] == "36+"
    assert len(d["belowMinimum"]) <= 10


def test_privacy_hides_small_states():
    d = build_dashboard(build_month(2026, 10))
    assert "AC" not in {s["id"] for s in d["stateWaste"]}  # AC tem 4 households no mock (mínimo 10)


def test_monthly_series_uses_history_in_chronological_order():
    history = [{"ano": 2026, "mes": 9, "dados": {"kpis": {"D1": {"valor": 14.0}}}},
               {"ano": 2026, "mes": 8, "dados": {"kpis": {"D1": {"valor": None}}}},
               {"ano": 2026, "mes": 7, "dados": {"kpis": {"D1": {"valor": 16.0}}}}]
    serie = build_dashboard(build_month(2026, 10), history)["monthlyWaste"]
    assert [p["id"] for p in serie] == ["2026-07", "2026-09", "2026-10"]  # agosto sem valor fica de fora
    assert [p["month"] for p in serie] == ["Jul", "Set", "Out"]
