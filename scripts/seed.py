"""Seed a development database: the single `orqen` tenant, the platform owner as its
admin and the author of one starter problem (3 sample and 5 hidden tests plus an active
eval rule), and two contestants on a free trial.

Users come from an `AuthProvider`. Against Supabase, `SupabaseAuth` creates them in
Supabase Auth through the admin API, and their Auth ids become `users.id`. Against
plain Postgres, such as CI, `StaticIds` derives the ids from the email instead.

Idempotent: every insert is ON CONFLICT DO NOTHING and Supabase users are looked up
before they are created, so running it twice changes nothing.

    uv run python -m scripts.seed
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from orqen_core.db import make_engine
from orqen_core.models import Role
from orqen_core.settings import get_settings

SEED_PASSWORD = os.environ.get("ORQEN_SEED_PASSWORD", "orqen-dev-password")
TENANT = "orqen"
OWNER = "owner@orqen.test"
CONTESTANTS = ("alice@orqen.test", "bob@orqen.test")
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


class AuthProvider(Protocol):
    async def ensure_user(self, email: str) -> UUID:
        """Return the auth user id for `email`, creating the user if needed."""
        ...


class StaticIds:
    """Plain Postgres has no auth service: derive a stable id from the email."""

    async def ensure_user(self, email: str) -> UUID:
        return sid("user", email)


class SupabaseAuth:
    """Creates users through the Supabase Auth admin API with the secret key."""

    def __init__(self, url: str, secret_key: str, password: str) -> None:
        headers = {"apikey": secret_key}
        if secret_key.startswith("eyJ"):  # a legacy service_role JWT also needs Bearer
            headers["Authorization"] = f"Bearer {secret_key}"
        self._client = httpx.AsyncClient(
            base_url=f"{url.rstrip('/')}/auth/v1/admin", headers=headers, timeout=15
        )
        self._password = password
        self._existing: dict[str, UUID] | None = None

    async def ensure_user(self, email: str) -> UUID:
        if self._existing is None:
            resp = await self._client.get("/users", params={"page": 1, "per_page": 1000})
            resp.raise_for_status()
            self._existing = {u["email"]: UUID(u["id"]) for u in resp.json()["users"]}
        if email not in self._existing:
            resp = await self._client.post(
                "/users",
                json={"email": email, "password": self._password, "email_confirm": True},
            )
            resp.raise_for_status()
            self._existing[email] = UUID(resp.json()["id"])
        return self._existing[email]

    async def aclose(self) -> None:
        await self._client.aclose()


async def insert(conn: AsyncConnection, table: str, row: dict[str, Any]) -> None:
    cols = ", ".join(row)
    params = ", ".join(f":{c}" for c in row)
    await conn.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({params}) ON CONFLICT DO NOTHING"), row
    )


# USD per million tokens, from Anthropic's price list. The proxy prices each call
# from the latest row for its model.
MODEL_PRICES = [(MODEL, datetime(2025, 10, 15, tzinfo=UTC), 1.00, 5.00)]


async def seed(conn: AsyncConnection, auth: AuthProvider) -> None:
    """The platform: model prices, the `orqen` tenant, its owner, two contestants and
    one problem."""
    for model, effective_from, input_price, output_price in MODEL_PRICES:
        await insert(
            conn,
            "billing.model_prices",
            {
                "model": model,
                "effective_from": effective_from,
                "input_usd_per_mtok": input_price,
                "output_usd_per_mtok": output_price,
            },
        )
    await seed_tenant(conn, auth, TENANT, "Orqen", OWNER, CONTESTANTS, platform_owner=True)


async def seed_tenant(
    conn: AsyncConnection,
    auth: AuthProvider,
    slug: str,
    name: str,
    admin_email: str,
    contestant_emails: tuple[str, ...],
    *,
    platform_owner: bool = False,
) -> UUID:
    """A tenant with one admin who authors the starter problem, and contestants on a
    free trial. Tests call this for a second tenant to check isolation.

    A trial starts when it is first seeded; later runs keep the existing row, so a
    contestant whose trial has ended needs a new subscription, not a reseed.
    """
    trial_start = datetime.now(UTC)
    tenant_id = sid("tenant", slug)
    await insert(conn, "identity.tenants", {"id": tenant_id, "slug": slug, "name": name})

    admin_id = await add_member(conn, auth, tenant_id, admin_email, Role.ADMIN, platform_owner)
    for email in contestant_emails:
        user_id = await add_member(conn, auth, tenant_id, email, Role.CONTESTANT)
        await insert(
            conn,
            "billing.subscriptions",
            {
                "id": sid("subscription", slug, email),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "plan_id": "free_trial",
                "status": "trialing",
                "current_period_start": trial_start,
                "current_period_end": trial_start + timedelta(days=7),
            },
        )

    problem_id = sid("problem", slug, PROBLEM_SLUG)
    await insert(
        conn,
        "authoring.problems",
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
            "created_by": admin_id,
        },
    )
    await insert(
        conn,
        "authoring.eval_rules",
        {
            "id": sid("eval_rule", slug, PROBLEM_SLUG, "1"),
            "tenant_id": tenant_id,
            "problem_id": problem_id,
            "version": 1,
            "spec": json.dumps(EVAL_RULE_V1),
            "status": "active",
            "created_by": admin_id,
        },
    )
    for ordinal, (raw, expected, is_sample) in enumerate(TESTS, start=1):
        await insert(
            conn,
            "authoring.test_cases",
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
    return tenant_id


async def add_member(
    conn: AsyncConnection,
    auth: AuthProvider,
    tenant_id: UUID,
    email: str,
    role: Role,
    platform_owner: bool = False,
) -> UUID:
    user_id = await auth.ensure_user(email)
    await insert(
        conn,
        "identity.users",
        {"id": user_id, "email": email, "is_platform_owner": platform_owner},
    )
    await insert(
        conn,
        "identity.memberships",
        {"tenant_id": tenant_id, "user_id": user_id, "role": role.value},
    )
    return user_id


async def has_auth_schema(conn: AsyncConnection) -> bool:
    found = await conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'auth'")
    )
    return found.first() is not None


async def main() -> None:
    settings = get_settings()
    key = settings.supabase_secret_key
    if key and key.get_secret_value().startswith("sb_publishable_"):
        sys.exit(
            "ORQEN_SUPABASE_SECRET_KEY holds a publishable key. The Auth admin API needs a "
            "secret key (sb_secret_...) from Settings > API Keys."
        )
    engine = make_engine(settings.database_url, pool_size=1)
    auth: AuthProvider
    supabase: SupabaseAuth | None = None
    try:
        async with engine.begin() as conn:
            if settings.supabase_url and settings.supabase_secret_key:
                supabase = SupabaseAuth(
                    settings.supabase_url,
                    settings.supabase_secret_key.get_secret_value(),
                    SEED_PASSWORD,
                )
                auth = supabase
            elif await has_auth_schema(conn):
                sys.exit(
                    "This database has Supabase's auth schema. Set ORQEN_SUPABASE_URL and "
                    "ORQEN_SUPABASE_SECRET_KEY so the seed can create users in Supabase Auth."
                )
            else:
                auth = StaticIds()
            await seed(conn, auth)
    finally:
        if supabase is not None:
            await supabase.aclose()
        await engine.dispose()
    logins = ", ".join((OWNER, *CONTESTANTS))
    where = f"Supabase Auth, password {SEED_PASSWORD!r}" if supabase else "no auth service"
    print(f"Seeded tenant {TENANT!r}. Users: {logins} ({where})", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
