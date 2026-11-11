"""Read routes. Each query runs as the caller's role, so row-level security decides what
comes back: contestants see listed problems, sample tests only, and their own
submissions.

    GET /v1/problems                       the problem set, with the caller's best
    GET /v1/problems/{id}                  statement, limits and sample tests
    GET /v1/problems/{id}/leaderboard      practice leaderboard by handle
    GET /v1/submissions                    the caller's recent submissions
    GET /v1/submissions/{id}               snapshot: status, score, seq and events
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from orqen_core.models import Mode, SubmissionStatus
from orqen_gateway.deps import AsMember
from orqen_gateway.live import stored_events

router = APIRouter(prefix="/v1")


class Limits(BaseModel):
    time_ms: int
    memory_mb: int
    token_budget: int
    max_steps: int
    models: list[str]


class ProblemSummary(BaseModel):
    problem_id: UUID
    slug: str
    title: str
    kinds: list[str]
    limits: Limits
    my_best: float | None
    solved_by: int


class SampleTest(BaseModel):
    ordinal: int
    input: Any
    expected: Any


class Problem(ProblemSummary):
    statement_md: str
    pass_mark: float
    samples: list[SampleTest]


class Standing(BaseModel):
    rank: int
    handle: str
    best_score: float
    reached_at: datetime
    you: bool


class SubmissionRow(BaseModel):
    submission_id: UUID
    problem_id: UUID
    problem_title: str
    mode: Mode
    status: SubmissionStatus
    score: float | None
    total_tests: int | None
    created_at: datetime


class Snapshot(SubmissionRow):
    problem_slug: str
    model: str | None
    prompt_chars: int
    total_tokens: int
    seq: int
    events: list[dict[str, Any]]


PROBLEM_COLUMNS = """
    p.id, p.slug, p.title, p.kinds, p.time_limit_ms, p.mem_limit_mb,
    p.token_budget_per_test, p.max_steps, p.models_allowed,
    (SELECT b.best_score FROM competition.practice_bests b
     WHERE b.problem_id = p.id AND b.user_id = :me) AS my_best,
    (SELECT count(*) FROM competition.practice_bests b
     WHERE b.problem_id = p.id AND b.best_score >= 100 * p.pass_mark) AS solved_by
"""


def summary(row: Any) -> dict[str, Any]:
    return {
        "problem_id": row.id,
        "slug": row.slug,
        "title": row.title,
        "kinds": row.kinds,
        "limits": Limits(
            time_ms=row.time_limit_ms,
            memory_mb=row.mem_limit_mb,
            token_budget=row.token_budget_per_test,
            max_steps=row.max_steps,
            models=row.models_allowed,
        ),
        "my_best": float(row.my_best) if row.my_best is not None else None,
        "solved_by": row.solved_by,
    }


@router.get("/problems")
async def list_problems(request: Request, who: AsMember) -> list[ProblemSummary]:
    async with who.tx(request.app.state.engine) as c:
        rows = (
            await c.execute(
                text(f"SELECT {PROBLEM_COLUMNS} FROM authoring.problems p ORDER BY p.created_at"),
                {"me": who.user_id},
            )
        ).all()
    return [ProblemSummary(**summary(r)) for r in rows]


@router.get("/problems/{problem_id}")
async def get_problem(request: Request, problem_id: UUID, who: AsMember) -> Problem:
    async with who.tx(request.app.state.engine) as c:
        row = (
            await c.execute(
                text(
                    f"SELECT {PROBLEM_COLUMNS}, p.statement_md, p.pass_mark"
                    " FROM authoring.problems p WHERE p.id = :id"
                ),
                {"id": problem_id, "me": who.user_id},
            )
        ).first()
        if row is None:
            raise HTTPException(404, "problem not found")
        samples = (
            await c.execute(
                text(
                    "SELECT ordinal, input, expected FROM authoring.test_cases"
                    " WHERE problem_id = :id AND is_sample ORDER BY ordinal"
                ),
                {"id": problem_id},
            )
        ).all()
    return Problem(
        **summary(row),
        statement_md=row.statement_md,
        pass_mark=float(row.pass_mark),
        samples=[
            SampleTest(ordinal=s.ordinal, input=s.input, expected=s.expected) for s in samples
        ],
    )


@router.get("/problems/{problem_id}/leaderboard")
async def problem_leaderboard(
    request: Request,
    problem_id: UUID,
    who: AsMember,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Standing]:
    async with who.tx(request.app.state.engine) as c:
        rows = (
            await c.execute(
                text(
                    """
                    SELECT u.handle, b.best_score, b.reached_at, b.user_id = :me AS you
                    FROM competition.practice_bests b
                    JOIN identity.users u ON u.id = b.user_id
                    WHERE b.problem_id = :p
                    ORDER BY b.best_score DESC, b.reached_at
                    LIMIT :limit
                    """
                ),
                {"p": problem_id, "me": who.user_id, "limit": limit},
            )
        ).all()
    return [
        Standing(
            rank=i,
            handle=r.handle,
            best_score=float(r.best_score),
            reached_at=r.reached_at,
            you=r.you,
        )
        for i, r in enumerate(rows, start=1)
    ]


SUBMISSION_COLUMNS = """
    s.id, s.problem_id, p.title AS problem_title, p.slug AS problem_slug, s.mode, s.status,
    s.score, s.total_tests, s.created_at, s.total_tokens, s.payload
"""


def submission_row(r: Any) -> dict[str, Any]:
    return {
        "submission_id": r.id,
        "problem_id": r.problem_id,
        "problem_title": r.problem_title,
        "mode": Mode(r.mode),
        "status": SubmissionStatus(r.status),
        "score": float(r.score) if r.score is not None else None,
        "total_tests": r.total_tests,
        "created_at": r.created_at,
    }


@router.get("/submissions")
async def list_submissions(
    request: Request,
    who: AsMember,
    problem_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[SubmissionRow]:
    async with who.tx(request.app.state.engine) as c:
        rows = (
            await c.execute(
                text(
                    f"""
                    SELECT {SUBMISSION_COLUMNS}
                    FROM judging.submissions s JOIN authoring.problems p ON p.id = s.problem_id
                    WHERE s.user_id = :me AND (CAST(:p AS uuid) IS NULL OR s.problem_id = :p)
                    ORDER BY s.created_at DESC LIMIT :limit
                    """
                ),
                {"me": who.user_id, "p": problem_id, "limit": limit},
            )
        ).all()
    return [SubmissionRow(**submission_row(r)) for r in rows]


@router.get("/submissions/{submission_id}")
async def get_submission(request: Request, submission_id: UUID, who: AsMember) -> Snapshot:
    """Everything the live view needs to render now, plus the `seq` to resume from.

    Events come from the stored event list. Once that has expired, they are rebuilt
    from `judging.test_results`, which holds one final row per test.
    """
    async with who.tx(request.app.state.engine) as c:
        r = (
            await c.execute(
                text(
                    f"SELECT {SUBMISSION_COLUMNS} FROM judging.submissions s"
                    " JOIN authoring.problems p ON p.id = s.problem_id WHERE s.id = :id"
                ),
                {"id": submission_id},
            )
        ).first()
        if r is None:
            raise HTTPException(404, "submission not found")
        redis: Redis = request.app.state.redis
        events = await stored_events(redis, who.tenant_id, submission_id)
        if not events:
            results = (
                await c.execute(
                    text(
                        """
                        SELECT tc.ordinal, tc.is_sample, r.test_case_id, r.verdict, r.score,
                               r.tokens, r.steps, r.latency_ms, r.created_at
                        FROM judging.test_results r
                        JOIN authoring.test_cases tc ON tc.id = r.test_case_id
                        WHERE r.submission_id = :id ORDER BY r.created_at
                        """
                    ),
                    {"id": submission_id},
                )
            ).all()
            events = [
                {
                    "seq": i,
                    "ts": t.created_at.isoformat(),
                    "type": "test",
                    "submission_id": str(submission_id),
                    "test": t.ordinal,
                    "test_case_id": str(t.test_case_id),
                    "kind": "sample" if t.is_sample else "hidden",
                    "verdict": t.verdict,
                    "score": float(t.score) if t.score is not None else None,
                    "tokens": t.tokens,
                    "steps": t.steps,
                    "latency_ms": t.latency_ms,
                }
                for i, t in enumerate(results, start=1)
            ]
    payload = r.payload or {}
    return Snapshot(
        **submission_row(r),
        problem_slug=r.problem_slug,
        model=payload.get("model"),
        prompt_chars=len(payload.get("prompt", "")),
        total_tokens=r.total_tokens,
        seq=max((int(e["seq"]) for e in events), default=0),
        events=events,
    )
