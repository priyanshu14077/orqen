import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core.db import DbRole, tenant_tx
from scripts import seed
from tests.conftest import RIVAL, seed_all

pytestmark = pytest.mark.integration


async def counts(engine: AsyncEngine) -> dict[str, int]:
    tables = [
        "identity.tenants",
        "identity.users",
        "identity.memberships",
        "authoring.problems",
        "authoring.problem_authors",
        "authoring.eval_rules",
        "authoring.test_cases",
    ]
    async with engine.connect() as conn:
        return {
            t: (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one() for t in tables
        }


async def test_the_seed_and_the_rival_tenant_have_a_problem_each(seeded: AsyncEngine) -> None:
    assert await counts(seeded) == {
        "identity.tenants": 2,
        "identity.users": 5,  # orqen: owner, alice, bob; rival: admin, carol
        "identity.memberships": 5,
        "authoring.problems": 2,
        "authoring.problem_authors": 2,
        "authoring.eval_rules": 2,
        "authoring.test_cases": 16,
    }
    async with seeded.connect() as conn:
        samples = (
            await conn.execute(text("SELECT count(*) FROM authoring.test_cases WHERE is_sample"))
        ).scalar_one()
    assert samples == 6


async def test_seed_is_idempotent(seeded: AsyncEngine) -> None:
    before = await counts(seeded)
    async with seeded.begin() as conn:
        await seed_all(conn)
    assert await counts(seeded) == before


async def test_a_test_case_cannot_point_at_another_tenants_problem(seeded: AsyncEngine) -> None:
    """The composite (tenant_id, problem_id) foreign key, not app code, stops this."""
    with pytest.raises(IntegrityError, match="foreign key"):
        async with seeded.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO authoring.test_cases "
                    "(tenant_id, problem_id, ordinal, input, expected) "
                    "VALUES (:tenant, :problem, 99, '{}', '{}')"
                ),
                {
                    "tenant": seed.sid("tenant", RIVAL),
                    "problem": seed.sid("problem", seed.TENANT, seed.PROBLEM_SLUG),
                },
            )


async def test_a_problem_has_at_most_one_active_eval_rule(seeded: AsyncEngine) -> None:
    with pytest.raises(IntegrityError, match="eval_rules_one_active_idx"):
        async with seeded.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO authoring.eval_rules "
                    "(tenant_id, problem_id, version, spec, status) "
                    "VALUES (:tenant, :problem, 2, :spec, 'active')"
                ),
                {
                    "tenant": seed.sid("tenant", seed.TENANT),
                    "problem": seed.sid("problem", seed.TENANT, seed.PROBLEM_SLUG),
                    "spec": json.dumps({}),
                },
            )


async def test_tenant_tx_runs_as_the_role_with_tenant_and_user_set(seeded: AsyncEngine) -> None:
    tenant_id = seed.sid("tenant", seed.TENANT)
    user_id = seed.sid("user", "alice@orqen.test")
    async with tenant_tx(seeded, tenant_id, DbRole.CONTESTANT, user_id) as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT current_user, current_setting('app.tenant_id'),"
                    " current_setting('app.user_id')"
                )
            )
        ).one()
    assert tuple(row) == (DbRole.CONTESTANT.value, str(tenant_id), str(user_id))

    # SET LOCAL must not outlive the transaction on a pooled connection.
    async with seeded.connect() as conn:
        role, tid = (
            await conn.execute(text("SELECT current_user, current_setting('app.tenant_id', true)"))
        ).one()
    assert role not in set(DbRole)
    assert not tid


async def test_a_person_role_needs_a_user(seeded: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="needs a user_id"):
        async with tenant_tx(seeded, uuid4(), DbRole.CONTESTANT):
            pass


async def test_no_role_can_rewrite_usage_history(seeded: AsyncEngine) -> None:
    with pytest.raises(Exception, match="permission denied"):
        async with tenant_tx(seeded, uuid4(), DbRole.WORKER) as conn:
            await conn.execute(text("DELETE FROM ops.llm_usage"))


async def test_every_user_is_a_supabase_auth_user(seeded: AsyncEngine) -> None:
    with pytest.raises(IntegrityError, match="users_auth_user_fk"):
        async with seeded.begin() as conn:
            await conn.execute(
                text("INSERT INTO identity.users (id, email) VALUES (:id, 'ghost@orqen.test')"),
                {"id": uuid4()},
            )


@pytest.mark.parametrize(
    "table",
    [
        "identity.tenants",
        "judging.submissions",
        "ops.llm_usage",
        "competition.contest_standings",
        "billing.subscriptions",
        "billing.paddle_events",
        "judging.sample_test_outputs",
        "public.alembic_version",
    ],
)
@pytest.mark.parametrize("role", ["anon", "authenticated", "service_role"])
async def test_the_data_api_roles_cannot_touch_orqen_tables(
    seeded: AsyncEngine, role: str, table: str
) -> None:
    """Supabase grants new public tables to anon and authenticated; 0002 revokes that, and
    the feature schemas from 0003 never grant them anything."""
    async with seeded.connect() as conn:
        allowed = (
            await conn.execute(
                text(
                    "SELECT has_table_privilege(:role, :table, 'SELECT')"
                    " OR has_table_privilege(:role, :table, 'INSERT')"
                    " OR has_table_privilege(:role, :table, 'TRUNCATE')"
                ),
                {"role": role, "table": table},
            )
        ).scalar_one()
    assert allowed is False


async def test_tables_created_later_are_not_granted_to_the_data_api(
    seeded: AsyncEngine,
) -> None:
    async with seeded.begin() as conn:
        await conn.execute(text("CREATE TABLE later_table (id int)"))
        try:
            allowed = (
                await conn.execute(
                    text("SELECT has_table_privilege('anon', 'later_table', 'SELECT')")
                )
            ).scalar_one()
        finally:
            await conn.execute(text("DROP TABLE later_table"))
    assert allowed is False


async def test_no_orqen_table_is_left_in_public(seeded: AsyncEngine) -> None:
    async with seeded.connect() as conn:
        tables = (
            (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            )
            .scalars()
            .all()
        )
    assert tables == ["alembic_version"]


async def test_the_plans_match_the_product_decisions(seeded: AsyncEngine) -> None:
    async with seeded.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, price_usd, credit_usd, period_days, submission_cap "
                    "FROM billing.plans ORDER BY id"
                )
            )
        ).all()
    assert [tuple(map(str, r)) for r in rows] == [
        ("free_trial", "0.00", "1.00", "7", "1"),
        ("pro", "20.00", "10.00", "None", "None"),
    ]


async def test_a_membership_role_must_be_admin_setter_or_contestant(
    seeded: AsyncEngine,
) -> None:
    with pytest.raises(IntegrityError, match="memberships_role_check"):
        async with seeded.begin() as conn:
            await conn.execute(
                text("UPDATE identity.memberships SET role = 'member' WHERE user_id = :u"),
                {"u": seed.sid("user", "alice@orqen.test")},
            )


async def subscribe(conn: AsyncConnection, plan: str, status: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO billing.subscriptions (tenant_id, user_id, plan_id, status, "
            "current_period_start, current_period_end) "
            "VALUES (:t, :u, :plan, :status, now(), now() + interval '7 days')"
        ),
        {
            "t": seed.sid("tenant", seed.TENANT),
            "u": seed.sid("user", "alice@orqen.test"),
            "plan": plan,
            "status": status,
        },
    )


async def test_a_user_gets_one_free_trial_ever(seeded: AsyncEngine) -> None:
    """The seed already started alice's trial."""
    with pytest.raises(IntegrityError, match="subscriptions_one_trial_idx"):
        async with seeded.begin() as conn:
            await subscribe(conn, "free_trial", "expired")


async def test_a_user_has_at_most_one_live_subscription(seeded: AsyncEngine) -> None:
    with pytest.raises(IntegrityError, match="subscriptions_one_live_idx"):
        async with seeded.begin() as conn:
            await subscribe(conn, "pro", "active")


async def test_a_contest_submission_must_target_a_problem_in_that_contest(
    seeded: AsyncEngine,
) -> None:
    tenant = seed.sid("tenant", seed.TENANT)
    async with seeded.connect() as conn:
        rule = (
            await conn.execute(
                text("SELECT id FROM authoring.eval_rules WHERE tenant_id = :t"), {"t": tenant}
            )
        ).scalar_one()
    with pytest.raises(IntegrityError, match="submissions_contest_fk"):
        async with seeded.begin() as conn:
            contest = (
                await conn.execute(
                    text(
                        "INSERT INTO competition.contests (tenant_id, slug, title, starts_at, "
                        "ends_at) VALUES (:t, 'empty-round', 'Empty', now(), "
                        "now() + interval '2 hours') RETURNING id"
                    ),
                    {"t": tenant},
                )
            ).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO judging.submissions (tenant_id, user_id, problem_id, "
                    "eval_rule_id, kind, mode, payload, contest_id) "
                    "VALUES (:t, :u, :p, :r, 'prompt', 'submit', '{}', :c)"
                ),
                {
                    "t": tenant,
                    "u": seed.sid("user", "alice@orqen.test"),
                    "p": seed.sid("problem", seed.TENANT, seed.PROBLEM_SLUG),
                    "r": rule,
                    "c": contest,
                },
            )
