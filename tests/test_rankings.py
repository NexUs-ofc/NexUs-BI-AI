from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.controller.ranking_controller import router
from app.repository import food_repository, ranking_repository
from app.schemas.api import CurrentUser


@pytest.fixture
def catalog(monkeypatch):
    lookup = MagicMock(return_value={10: "Arroz", 20: "Banana", 30: "Leite"})
    monkeypatch.setattr(food_repository, "find_food_names", lookup)
    return lookup


@pytest.fixture
def redis(monkeypatch):
    client = MagicMock()
    client.zrevrange.side_effect = [
        [("20", 8.0), ("10", 4.0)],
        [("30", 3.0), ("20", 2.0)],
    ]
    monkeypatch.setattr(ranking_repository, "_get_redis", lambda: client)
    return client


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(profile_id=1)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("query, suffix, state", [("", "all", None), ("?state=sp", "state:SP", "SP")])
def test_rankings_resolve_food_names_and_preserve_order(api, redis, catalog, query, suffix, state):
    response = api.get("/api/rankings/products" + query)

    assert response.status_code == 200
    assert response.json() == {
        "registered": [
            {"productId": "20", "productName": "Banana", "score": 8.0},
            {"productId": "10", "productName": "Arroz", "score": 4.0},
        ],
        "expired": [
            {"productId": "30", "productName": "Leite", "score": 3.0},
            {"productId": "20", "productName": "Banana", "score": 2.0},
        ],
        "state": state,
    }
    catalog.assert_called_once_with([10, 20, 30])
    assert redis.zrevrange.call_args_list == [
        ((f"ranking:product:registered:{suffix}", 0, 4), {"withscores": True}),
        ((f"ranking:product:expired:{suffix}", 0, 4), {"withscores": True}),
    ]


def test_unknown_and_legacy_members_are_not_returned_as_food_names(api, redis, catalog):
    redis.zrevrange.side_effect = [
        [("Banana", 12540.0), ("99", 20.0), ("10", 4.0), ("2147483648", 2.0)],
        [("-1", 9.0), ("0", 8.0), ("01", 7.0), ("١٠", 6.0)],
    ]
    response = api.get("/api/rankings/products")

    assert response.status_code == 200
    assert response.json()["registered"] == [{"productId": "10", "productName": "Arroz", "score": 4.0}]
    assert response.json()["expired"] == []
    catalog.assert_called_once_with([10, 99])


def test_empty_state_is_not_filled_with_general_ranking(api, redis, catalog):
    redis.zrevrange.side_effect = [[], []]
    catalog.return_value = {}

    response = api.get("/api/rankings/products?state=AC")

    assert response.status_code == 200
    assert response.json() == {"registered": [], "expired": [], "state": "AC"}
    assert all(call.args[0].endswith("state:AC") for call in redis.zrevrange.call_args_list)
    catalog.assert_called_once_with([])


@pytest.mark.parametrize("state", ["XX", "S", "SPX"])
def test_invalid_state_is_rejected_before_accessing_data(api, redis, catalog, state):
    assert api.get("/api/rankings/products", params={"state": state}).status_code == 422
    redis.zrevrange.assert_not_called()
    catalog.assert_not_called()


def test_redis_failure_is_not_reported_as_empty_ranking(api, redis, catalog):
    redis.zrevrange.side_effect = ConnectionError("Redis unavailable")

    response = api.get("/api/rankings/products")

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço de rankings temporariamente indisponível."}
    catalog.assert_not_called()


def test_catalog_failure_is_not_reported_as_empty_ranking(api, redis, catalog):
    catalog.side_effect = psycopg.OperationalError("private database connection details")

    response = api.get("/api/rankings/products")

    assert response.status_code == 503
    assert response.json() == {"detail": "Serviço de rankings temporariamente indisponível."}


def test_food_names_are_fetched_in_one_parameterized_query(monkeypatch):
    connect = MagicMock()
    connection = connect.return_value.__enter__.return_value
    connection.execute.return_value.fetchall.return_value = [(20, "Banana"), (10, "Arroz")]
    monkeypatch.setattr(food_repository, "PGSQL_URL", "postgresql://catalog.test/nexus")
    monkeypatch.setattr(food_repository.psycopg, "connect", connect)

    assert food_repository.find_food_names([10, 20]) == {10: "Arroz", 20: "Banana"}
    connect.assert_called_once_with("postgresql://catalog.test/nexus", connect_timeout=5)
    connection.execute.assert_called_once_with(
        "SELECT id, name FROM public.food WHERE id = ANY(%s)",
        ([10, 20],),
    )


def test_empty_food_ids_do_not_connect_to_postgres(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(food_repository.psycopg, "connect", connect)

    assert food_repository.find_food_names([]) == {}
    connect.assert_not_called()


def test_catalog_requires_postgres_configuration(monkeypatch):
    monkeypatch.setattr(food_repository, "PGSQL_URL", "")

    with pytest.raises(RuntimeError, match="PGSQL_URL"):
        food_repository.find_food_names([10])
