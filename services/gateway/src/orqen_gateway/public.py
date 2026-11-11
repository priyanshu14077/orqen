"""Public, signed-out reads for the landing page.

    GET /v1/public/arena    listed problems, the overall leaderboard and two counts

The query runs as `orqen_contestant` for a user who doesn't exist, so row-level
security returns exactly what any contestant may see: listed problems, handles and
best scores. Emails, hidden tests and anyone's submissions stay out of reach, because
that role has no grant or policy for them. The response is the same for every caller,
so it is cached in-process for `CACHE_S` seconds; a burst of visitors costs one query.
"""

import time
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text

from orqen_core.db import DbRole, tenant_tx
from orqen_gateway.deps import Tenant

router = APIRouter(prefix="/v1/public")

CACHE_S = 30
NOBODY = UUID(int=0)
LEADERS = 10


class ArenaProblem(BaseModel):
    slug: str
    title: str
    kinds: list[str]
    time_ms: int
    token_budget: int
    max_steps: int
    solved_by: int
    attempted_by: int


class ArenaLeader(BaseModel):
    rank: int
    handle: str
    solved: int
    total_score: float
    last_at: datetime


class Arena(BaseModel):
    problems: list[ArenaProblem]
    leaders: list[ArenaLeader]
    ranked_agents: int


@router.get("/arena")
async def arena(request: Request, response: Response, tenant_id: Tenant) -> Arena:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_S}"
    cached: tuple[float, Arena] | None = getattr(request.app.state, "arena", None)
    if cached and time.monotonic() - cached[0] < CACHE_S:
        return cached[1]

    async with tenant_tx(request.app.state.engine, tenant_id, DbRole.CONTESTANT, NOBODY) as c:
        problems = (
            await c.execute(
                text(
                    """
                    SELECT p.slug, p.title, p.kinds, p.time_limit_ms, p.token_budget_per_test,
                           p.max_steps,
                           count(b.user_id) FILTER (WHERE b.best_score >= 100 * p.pass_mark)
                               AS solved_by,
                           count(b.user_id) AS attempted_by
                    FROM authoring.problems p
                    LEFT JOIN competition.practice_bests b ON b.problem_id = p.id
                    GROUP BY p.id
                    ORDER BY p.created_at
                    """
                )
            )
        ).all()
        leaders = (
            await c.execute(
                text(
                    """
                    SELECT u.handle,
                           count(*) FILTER (WHERE b.best_score >= 100 * p.pass_mark) AS solved,
                           sum(b.best_score) AS total_score,
                           max(b.reached_at) AS last_at
                    FROM competition.practice_bests b
                    JOIN authoring.problems p ON p.id = b.problem_id
                    JOIN identity.users u ON u.id = b.user_id
                    GROUP BY u.id, u.handle
                    ORDER BY total_score DESC, last_at
                    LIMIT :n
                    """
                ),
                {"n": LEADERS},
            )
        ).all()
        ranked = (
            await c.execute(text("SELECT count(DISTINCT user_id) FROM competition.practice_bests"))
        ).scalar_one()

    result = Arena(
        problems=[
            ArenaProblem(
                slug=p.slug,
                title=p.title,
                kinds=p.kinds,
                time_ms=p.time_limit_ms,
                token_budget=p.token_budget_per_test,
                max_steps=p.max_steps,
                solved_by=p.solved_by,
                attempted_by=p.attempted_by,
            )
            for p in problems
        ],
        leaders=[
            ArenaLeader(
                rank=i,
                handle=r.handle,
                solved=r.solved,
                total_score=float(r.total_score),
                last_at=r.last_at,
            )
            for i, r in enumerate(leaders, start=1)
        ],
        ranked_agents=ranked,
    )
    request.app.state.arena = (time.monotonic(), result)
    return result
