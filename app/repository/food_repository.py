import psycopg

from app.config import PGSQL_URL


def find_food_names(food_ids: list[int]) -> dict[int, str]:
    if not food_ids:
        return {}
    if not PGSQL_URL:
        raise RuntimeError("PGSQL_URL não definida.")
    with psycopg.connect(PGSQL_URL, connect_timeout=5) as connection:
        rows = connection.execute(
            "SELECT id, name FROM public.food WHERE id = ANY(%s)",
            (food_ids,),
        ).fetchall()
    return dict(rows)
