import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core.db import APP_ROLE, tenant_tx
from scripts import seed

pytestmark = pytest.mark.integration


async def counts(engine: AsyncEngine) -> dict[str, int]:
    tables = ["tenants", "users", "memberships", "problems", "eval_rules", "test_cases"]
    async with engine.connect() as conn:
        return {
            t: (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one() for t in tables
        }


@pytest.fixture(scope="module")
async def seeded(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await seed.seed(conn)
    return engine


async def test_seed_creates_two_tenants_with_a_problem_each(seeded: AsyncEngine) -> None:
    assert await counts(seeded) == {
        "tenants": 2,
        "users": 5,  # owner + admin and member per tenant
        "memberships": 4,
        "problems": 2,
        "eval_rules": 2,
        "test_cases": 16,
    }
    async with seeded.connect() as conn:
        samples = (
            await conn.execute(text("SELECT count(*) FROM test_cases WHERE is_sample"))
        ).scalar_one()
    assert samples == 6


async def test_seed_is_idempotent(seeded: AsyncEngine) -> None:
    before = await counts(seeded)
    async with seeded.begin() as conn:
        await seed.seed(conn)
    assert await counts(seeded) == before


async def test_a_test_case_cannot_point_at_another_tenants_problem(seeded: AsyncEngine) -> None:
    """The composite (tenant_id, problem_id) foreign key, not app code, stops this."""
    with pytest.raises(IntegrityError, match="foreign key"):
        async with seeded.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO test_cases (tenant_id, problem_id, ordinal, input, expected) "
                    "VALUES (:tenant, :problem, 99, '{}', '{}')"
                ),
                {
                    "tenant": seed.sid("tenant", "globex"),
                    "problem": seed.sid("problem", "acme", seed.PROBLEM_SLUG),
                },
            )


async def test_a_problem_has_at_most_one_active_eval_rule(seeded: AsyncEngine) -> None:
    with pytest.raises(IntegrityError, match="eval_rules_one_active_idx"):
        async with seeded.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO eval_rules (tenant_id, problem_id, version, spec, status) "
                    "VALUES (:tenant, :problem, 2, :spec, 'active')"
                ),
                {
                    "tenant": seed.sid("tenant", "acme"),
                    "problem": seed.sid("problem", "acme", seed.PROBLEM_SLUG),
                    "spec": json.dumps({}),
                },
            )


async def test_tenant_tx_runs_as_the_app_role_with_the_tenant_set(seeded: AsyncEngine) -> None:
    tenant_id = seed.sid("tenant", "acme")
    async with tenant_tx(seeded, tenant_id) as conn:
        role, tid = (
            await conn.execute(text("SELECT current_user, current_setting('app.tenant_id')"))
        ).one()
    assert (role, tid) == (APP_ROLE, str(tenant_id))

    # SET LOCAL must not outlive the transaction on a pooled connection.
    async with seeded.connect() as conn:
        role, tid = (
            await conn.execute(text("SELECT current_user, current_setting('app.tenant_id', true)"))
        ).one()
    assert role != APP_ROLE
    assert not tid


async def test_the_app_role_cannot_rewrite_usage_history(seeded: AsyncEngine) -> None:
    with pytest.raises(Exception, match="permission denied"):
        async with tenant_tx(seeded, uuid4()) as conn:
            await conn.execute(text("DELETE FROM llm_usage"))
