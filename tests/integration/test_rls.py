"""Row-level security and grants from migration 0004, checked role by role.

Each test runs in one transaction that is rolled back, so nothing it writes leaks into
other tests. Setup rows are written as the table owner, which bypasses RLS; `act`
then switches to the role under test, the way orqen_core.db.tenant_tx does.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core.db import DbRole
from scripts import seed
from tests.conftest import RIVAL

pytestmark = pytest.mark.integration

ORQEN = seed.sid("tenant", seed.TENANT)
RIVAL_TENANT = seed.sid("tenant", RIVAL)
AUTHOR = seed.sid("user", seed.OWNER)  # admin, and author of the starter problem
CONTESTANT = seed.sid("user", "alice@orqen.test")
PROBLEM = seed.sid("problem", seed.TENANT, seed.PROBLEM_SLUG)

SCHEMAS = ("identity", "authoring", "judging", "competition", "billing", "ops")


@pytest.fixture
async def conn(seeded: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with seeded.connect() as c:
        tx = await c.begin()
        try:
            yield c
        finally:
            await tx.rollback()


async def act(
    c: AsyncConnection, role: DbRole, user: UUID | None = None, tenant: UUID = ORQEN
) -> None:
    await c.execute(text("RESET ROLE"))
    await c.execute(text(f"SET LOCAL ROLE {role.value}"))
    await c.execute(
        text("SELECT set_config('app.tenant_id', :t, true), set_config('app.user_id', :u, true)"),
        {"t": str(tenant), "u": str(user) if user else ""},
    )


async def as_owner(c: AsyncConnection) -> None:
    await c.execute(text("RESET ROLE"))


async def scalar(c: AsyncConnection, sql: str, /, **params: Any) -> Any:
    return (await c.execute(text(sql), params)).scalar_one()


async def fails(c: AsyncConnection, sql: str, match: str, /, **params: Any) -> None:
    """Run `sql` in a savepoint and assert it fails with `match`."""
    sp = await c.begin_nested()
    with pytest.raises(DBAPIError, match=match):
        await c.execute(text(sql), params)
    await sp.rollback()


async def submit(
    c: AsyncConnection, user: UUID, contest: UUID | None = None, mode: str = "submit"
) -> Any:
    return (
        await c.execute(
            text(
                "INSERT INTO judging.submissions "
                "(tenant_id, user_id, problem_id, contest_id, kind, mode, payload) "
                "VALUES (:t, :u, :p, :c, 'prompt', :mode, '{}') "
                "RETURNING id, ranked, eval_rule_id IS NOT NULL AS pinned, status"
            ),
            {"t": ORQEN, "u": user, "p": PROBLEM, "c": contest, "mode": mode},
        )
    ).one()


async def contest(c: AsyncConnection, starts: str, ends: str) -> UUID:
    """Owner-only: a published contest holding the starter problem as A."""
    contest_id: UUID = await scalar(
        c,
        "INSERT INTO competition.contests (tenant_id, slug, title, starts_at, ends_at, "
        "visibility) VALUES (:t, 'round-1', 'Round 1', now() + CAST(:s AS interval), "
        "now() + CAST(:e AS interval), 'published') RETURNING id",
        t=ORQEN,
        s=starts,
        e=ends,
    )
    await c.execute(
        text(
            "INSERT INTO competition.contest_problems (tenant_id, contest_id, problem_id, "
            "label, ordinal) VALUES (:t, :c, :p, 'A', 1)"
        ),
        {"t": ORQEN, "c": contest_id, "p": PROBLEM},
    )
    return contest_id


async def test_every_table_has_rls_on_and_at_least_one_policy(conn: AsyncConnection) -> None:
    missing = (
        (
            await conn.execute(
                text(
                    "SELECT c.oid::regclass::text FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = ANY(:s) AND c.relkind = 'r' AND (NOT c.relrowsecurity "
                    "OR NOT EXISTS (SELECT FROM pg_policy p WHERE p.polrelid = c.oid))"
                ),
                {"s": list(SCHEMAS)},
            )
        )
        .scalars()
        .all()
    )
    assert missing == []


async def test_orqen_app_has_no_privileges_left(conn: AsyncConnection) -> None:
    grants = await scalar(
        conn,
        "SELECT count(*) FROM information_schema.role_table_grants WHERE grantee = 'orqen_app'",
    )
    assert grants == 0


async def test_a_contestant_sees_published_problems_of_their_tenant_only(
    conn: AsyncConnection,
) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT array_agg(id) FROM authoring.problems") == [PROBLEM]


async def test_a_contestant_sees_sample_tests_only(conn: AsyncConnection) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT count(*) FROM authoring.test_cases") == 3
    assert await scalar(conn, "SELECT bool_and(is_sample) FROM authoring.test_cases")


async def test_a_contestant_cannot_read_eval_rules(conn: AsyncConnection) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    await fails(conn, "SELECT * FROM authoring.eval_rules", "permission denied")


async def test_a_submission_is_ranked_and_pinned_to_the_active_rule(
    conn: AsyncConnection,
) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    _, ranked, pinned, status = await submit(conn, CONTESTANT)
    assert (ranked, pinned, status) == (True, True, "QUEUED")


async def test_a_submission_to_your_own_problem_is_unranked(conn: AsyncConnection) -> None:
    await act(conn, DbRole.ADMIN, AUTHOR)
    _, ranked, _, _ = await submit(conn, AUTHOR)
    assert ranked is False


async def test_a_contestant_cannot_submit_as_someone_else(conn: AsyncConnection) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    await fails(
        conn,
        "INSERT INTO judging.submissions (tenant_id, user_id, problem_id, kind, mode, payload)"
        " VALUES (:t, :u, :p, 'prompt', 'submit', '{}')",
        "row-level security",
        t=ORQEN,
        u=AUTHOR,
        p=PROBLEM,
    )


async def test_a_contestant_cannot_choose_their_score(conn: AsyncConnection) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    await fails(
        conn,
        "INSERT INTO judging.submissions (tenant_id, user_id, problem_id, kind, mode, payload,"
        " score) VALUES (:t, :u, :p, 'prompt', 'submit', '{}', 1)",
        "permission denied",
        t=ORQEN,
        u=CONTESTANT,
        p=PROBLEM,
    )


async def test_a_contestant_sees_only_their_own_practice_submissions(
    conn: AsyncConnection,
) -> None:
    await act(conn, DbRole.ADMIN, AUTHOR)
    await submit(conn, AUTHOR)
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    mine, _, _, _ = await submit(conn, CONTESTANT)
    assert await scalar(conn, "SELECT array_agg(id) FROM judging.submissions") == [mine]

    await act(conn, DbRole.ADMIN, AUTHOR)
    assert await scalar(conn, "SELECT count(*) FROM judging.submissions") == 2


async def test_hidden_test_outputs_stay_hidden(conn: AsyncConnection) -> None:
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    sub, _, _, _ = await submit(conn, CONTESTANT)
    await as_owner(conn)
    await conn.execute(
        text(
            "INSERT INTO judging.test_results (submission_id, test_case_id, tenant_id, verdict,"
            " output, judge_reason) SELECT :s, id, tenant_id, 'FAIL', '{\"leak\": 1}', 'quoted'"
            " FROM authoring.test_cases WHERE problem_id = :p AND ordinal IN (1, 4)"
        ),
        {"s": sub, "p": PROBLEM},
    )

    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT count(verdict) FROM judging.test_results") == 2
    await fails(conn, "SELECT output FROM judging.test_results", "permission denied")
    await fails(conn, "SELECT judge_reason FROM judging.test_results", "permission denied")
    assert await scalar(conn, "SELECT count(*) FROM judging.sample_test_outputs") == 1


async def test_a_problem_in_an_upcoming_contest_is_hidden(conn: AsyncConnection) -> None:
    await contest(conn, "1 hour", "3 hours")
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT count(*) FROM authoring.problems") == 0
    assert await scalar(conn, "SELECT count(*) FROM authoring.test_cases") == 0
    assert await scalar(conn, "SELECT count(*) FROM competition.contest_problems") == 0


async def test_during_a_contest_its_problems_take_contest_submits_only(
    conn: AsyncConnection,
) -> None:
    running = await contest(conn, "-1 hour", "1 hour")
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT count(*) FROM authoring.problems") == 1
    await fails(
        conn,
        "INSERT INTO judging.submissions (tenant_id, user_id, problem_id, kind, mode, payload)"
        " VALUES (:t, :u, :p, 'prompt', 'submit', '{}')",
        "row-level security",
        t=ORQEN,
        u=CONTESTANT,
        p=PROBLEM,
    )
    _, ranked, _, _ = await submit(conn, CONTESTANT, contest=running)
    assert ranked is True


async def test_contest_code_is_public_only_after_the_contest_ends(
    conn: AsyncConnection,
) -> None:
    ended = await contest(conn, "-3 hours", "-1 hour")
    # Owner-only: the contest is over, so nobody could submit to it now.
    other = await scalar(
        conn,
        "INSERT INTO judging.submissions (tenant_id, user_id, problem_id, contest_id, kind,"
        " mode, payload) VALUES (:t, :u, :p, :c, 'prompt', 'submit', '{}') RETURNING id",
        t=ORQEN,
        u=AUTHOR,
        p=PROBLEM,
        c=ended,
    )
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT array_agg(id) FROM judging.submissions") == [other]

    await as_owner(conn)
    await conn.execute(text("UPDATE competition.contests SET ends_at = now() + interval '1 hour'"))
    await act(conn, DbRole.CONTESTANT, CONTESTANT)
    assert await scalar(conn, "SELECT count(*) FROM judging.submissions") == 0


async def test_a_new_problem_belongs_to_its_setter(conn: AsyncConnection) -> None:
    await act(conn, DbRole.SETTER, CONTESTANT)
    draft = await scalar(
        conn,
        "INSERT INTO authoring.problems (tenant_id, slug, title, statement_md, models_allowed,"
        " time_limit_ms, mem_limit_mb, token_budget_per_test, max_steps, created_by)"
        " VALUES (:t, 'draft-one', 'Draft', '', '{claude-haiku-4-5}', 1000, 64, 100, 1, :u)"
        " RETURNING id",
        t=ORQEN,
        u=CONTESTANT,
    )
    await conn.execute(
        text(
            "INSERT INTO authoring.test_cases (tenant_id, problem_id, ordinal, input, expected)"
            " VALUES (:t, :p, 1, '{}', '{}')"
        ),
        {"t": ORQEN, "p": draft},
    )
    # The seed problem belongs to someone else: the setter may read it, not edit it.
    edited = await conn.execute(
        text("UPDATE authoring.problems SET title = 'mine now' WHERE id = :p"), {"p": PROBLEM}
    )
    assert edited.rowcount == 0

    await act(conn, DbRole.CONTESTANT, AUTHOR)
    assert await scalar(conn, "SELECT count(*) FROM authoring.problems WHERE id = :p", p=draft) == 0


async def test_a_worker_sees_only_the_tenant_it_is_scoped_to(conn: AsyncConnection) -> None:
    await act(conn, DbRole.WORKER, tenant=RIVAL_TENANT)
    assert (
        await scalar(conn, "SELECT count(*) FROM authoring.problems WHERE id = :p", p=PROBLEM) == 0
    )
    assert await scalar(conn, "SELECT count(*) FROM authoring.test_cases") == 8


async def test_no_tenant_set_means_no_rows(conn: AsyncConnection) -> None:
    await act(conn, DbRole.WORKER)
    await conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    assert await scalar(conn, "SELECT count(*) FROM authoring.problems") == 0
