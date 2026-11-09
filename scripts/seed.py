"""Seed a development database: 2 tenants, an admin and a member in each, a platform
owner, and one problem per tenant with 3 sample and 5 hidden tests plus an active
eval rule.

Idempotent: ids are derived from names (uuid5), and every insert is
ON CONFLICT DO NOTHING, so running it twice changes nothing.

    uv run python -m scripts.seed
"""

import asyncio
import json
import os
import sys
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from orqen_core.db import make_engine
from orqen_core.security import hash_password
from orqen_core.settings import get_settings

SEED_PASSWORD = os.environ.get("ORQEN_SEED_PASSWORD", "orqen-dev-password")
TENANTS = [("acme", "Acme Corp"), ("globex", "Globex")]
PROBLEM_SLUG = "invoice-extractor"
MODEL = "claude-haiku-4-5"


def sid(*parts: str) -> UUID:
    """A stable id for a seed row, so tests and docs can refer to it."""
    return uuid5(NAMESPACE_URL, "orqen-seed:" + ":".join(parts))


STATEMENT = """\
Extract `vendor`, `date` (ISO 8601), `total` (number) and `currency` (ISO 4217)
from messy invoice text. Return a JSON object with exactly those four keys.
"""

# (text, expected, is_sample)
TESTS: list[tuple[str, dict[str, Any], bool]] = [
    (
        "INVOICE #1182 from Northwind Traders, dated 3 March 2026. Amount due: $1,240.50",
        {"vendor": "Northwind Traders", "date": "2026-03-03", "total": 1240.5, "currency": "USD"},
        True,
    ),
    (
        "Rechnung - Müller GmbH - 12.01.2026 - Gesamt 89,90 EUR",
        {"vendor": "Müller GmbH", "date": "2026-01-12", "total": 89.9, "currency": "EUR"},
        True,
    ),
    (
        "bill from tata consultancy dt 2026-02-28 total INR 45,000",
        {"vendor": "Tata Consultancy", "date": "2026-02-28", "total": 45000, "currency": "INR"},
        True,
    ),
    (
        "Contoso Ltd | Inv 77 | 15/04/2026 | GBP 312.00 incl. VAT",
        {"vendor": "Contoso Ltd", "date": "2026-04-15", "total": 312.0, "currency": "GBP"},
        False,
    ),
    (
        "Payment request: Initech, May 1st 2026, total due 7.5k USD",
        {"vendor": "Initech", "date": "2026-05-01", "total": 7500, "currency": "USD"},
        False,
    ),
    (
        "¥98,000 — Sakura Shoji K.K. — 2026年6月10日",
        {"vendor": "Sakura Shoji K.K.", "date": "2026-06-10", "total": 98000, "currency": "JPY"},
        False,
    ),
    (
        "Umbrella Corp invoice. Subtotal 100 CAD, tax 13 CAD, TOTAL 113 CAD. Date: 2026-07-07",
        {"vendor": "Umbrella Corp", "date": "2026-07-07", "total": 113, "currency": "CAD"},
        False,
    ),
    (
        "From: Hooli <billing@hooli.example> Sent 2026-08-19. Your total is AUD 64.20",
        {"vendor": "Hooli", "date": "2026-08-19", "total": 64.2, "currency": "AUD"},
        False,
    ),
]

EVAL_RULE_V1: dict[str, Any] = {
    "grading": {
        "gates": [
            {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "required": ["vendor", "date", "total", "currency"],
                },
            },
            {"type": "json_fields", "fields": ["date", "currency"]},
            {"type": "numeric_tolerance", "field": "total", "abs_tol": 0.01},
        ],
        "judge": None,
        "pass_threshold": 1.0,
    }
}


async def insert(conn: AsyncConnection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(row)
    params = ", ".join(f":{c}" for c in row)
    await conn.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({params}) ON CONFLICT DO NOTHING"), row
    )


async def seed(conn: AsyncConnection) -> None:
    pw = hash_password(SEED_PASSWORD)
    await insert(
        conn,
        "users",
        {
            "id": sid("user", "owner"),
            "email": "owner@orqen.test",
            "password_hash": pw,
            "is_platform_owner": True,
        },
    )

    for slug, name in TENANTS:
        tenant_id = sid("tenant", slug)
        await insert(conn, "tenants", {"id": tenant_id, "slug": slug, "name": name})

        for role in ("admin", "member"):
            user_id = sid("user", slug, role)
            await insert(
                conn,
                "users",
                {"id": user_id, "email": f"{role}@{slug}.test", "password_hash": pw},
            )
            await insert(
                conn, "memberships", {"tenant_id": tenant_id, "user_id": user_id, "role": role}
            )

        problem_id = sid("problem", slug, PROBLEM_SLUG)
        await insert(
            conn,
            "problems",
            {
                "id": problem_id,
                "tenant_id": tenant_id,
                "slug": PROBLEM_SLUG,
                "title": "Invoice Extractor",
                "statement_md": STATEMENT,
                "models_allowed": [MODEL],
                "time_limit_ms": 60_000,
                "mem_limit_mb": 256,
                "token_budget_per_test": 8_000,
                "max_steps": 6,
                "visibility": "published",
                "created_by": sid("user", slug, "admin"),
            },
        )
        await insert(
            conn,
            "eval_rules",
            {
                "id": sid("eval_rule", slug, PROBLEM_SLUG, "1"),
                "tenant_id": tenant_id,
                "problem_id": problem_id,
                "version": 1,
                "spec": json.dumps(EVAL_RULE_V1),
                "status": "active",
                "created_by": sid("user", slug, "admin"),
            },
        )
        for ordinal, (raw, expected, is_sample) in enumerate(TESTS, start=1):
            await insert(
                conn,
                "test_cases",
                {
                    "id": sid("test_case", slug, PROBLEM_SLUG, str(ordinal)),
                    "tenant_id": tenant_id,
                    "problem_id": problem_id,
                    "ordinal": ordinal,
                    "input": json.dumps({"text": raw}),
                    "expected": json.dumps(expected),
                    "is_sample": is_sample,
                },
            )


async def main(database_url: str | None = None) -> None:
    engine = make_engine(database_url or get_settings().database_url, pool_size=1)
    try:
        async with engine.begin() as conn:
            await seed(conn)
    finally:
        await engine.dispose()
    print(
        f"Seeded tenants {[t for t, _ in TENANTS]}. "
        f"Logins: owner@orqen.test, admin@<tenant>.test, member@<tenant>.test "
        f"(password: {SEED_PASSWORD!r})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
