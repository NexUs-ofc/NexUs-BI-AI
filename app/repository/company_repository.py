"""Company lookup in the Auth service's PostgreSQL database (read-only).

Tables written by the Auth service (NexUs-Auth):
- profile(id, type, status): type is HOUSEHOLD | ADMIN | COMPANY | STORE; status is ACTIVE | INACTIVE | BLOCKED
- company(id, profile_id, cnpj, plan_id): one row per company profile
"""
import psycopg

from app.config import PGSQL_URL

ACTIVE_COMPANY_QUERY = """
    SELECT c.id
    FROM company c
    JOIN profile p ON p.id = c.profile_id
    WHERE p.id = %s AND p.type = 'COMPANY' AND p.status = 'ACTIVE'
"""


def find_active_company_id(profile_id: int) -> int | None:
    """Return the company id of an ACTIVE company profile, or None if it does not exist / is not active."""
    if not PGSQL_URL:
        raise RuntimeError("PGSQL_URL não definida. Preencha o arquivo .env (veja .env.example).")
    with psycopg.connect(PGSQL_URL, connect_timeout=5) as connection:
        row = connection.execute(ACTIVE_COMPANY_QUERY, (profile_id,)).fetchone()
    return row[0] if row else None
