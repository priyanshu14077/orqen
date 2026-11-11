"""The v1 API: account provisioning and submissions.

Every route needs a Supabase access token. Queries run in `tenant_tx` as the caller's
database role, so row-level security decides what a caller may read and write; the
gateway adds no checks of its own beyond mapping database refusals to HTTP.

    GET  /v1/me                  the caller's account
    POST /v1/me                  create the Orqen account on first sign-in
    POST /v1/submissions         queue a submission (202)

Reads live in `reads.py`, the live event stream in `live.py`.
"""

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core import keys, streams
from orqen_core.db import DbRole, tenant_tx
from orqen_core.logging import get_logger
from orqen_core.models import Mode, Role, SubmissionMsg, SubmissionStatus
from orqen_gateway.deps import Caller, Tenant, member_role, refusal

log = get_logger(__name__)
router = APIRouter(prefix="/v1")

# ---------------------------------------------------------------------------- /v1/me


class MeOut(BaseModel):
    user_id: UUID
    handle: str
    role: Role
    plan_id: str | None
    subscription_status: str | None


@router.post("/me")
async def me(request: Request, caller: Caller, tenant_id: Tenant) -> MeOut:
    """Create the caller's user row, contestant membership and free trial if missing.

    Safe to call on every sign-in: each insert skips rows that exist, and the
    one-trial-per-user index stops a second trial.
    """
    if caller.email is None:
        raise HTTPException(400, "the token carries no email")
    async with tenant_tx(request.app.state.engine, tenant_id, DbRole.WORKER) as c:
        params = {"t": tenant_id, "u": caller.user_id, "email": caller.email}
        await c.execute(
            text(
                "INSERT INTO identity.users (id, email) VALUES (:u, :email)"
                " ON CONFLICT (id) DO NOTHING"
            ),
            params,
        )
        await c.execute(
            text(
                "INSERT INTO identity.memberships (tenant_id, user_id, role)"
                " VALUES (:t, :u, 'contestant') ON CONFLICT DO NOTHING"
            ),
            params,
        )
        await c.execute(
            text(
                """
                INSERT INTO billing.subscriptions (tenant_id, user_id, plan_id, status,
                    current_period_start, current_period_end)
                SELECT :t, :u, id, 'trialing', now(), now() + make_interval(days => period_days)
                FROM billing.plans WHERE is_trial AND active
                ORDER BY id LIMIT 1
                ON CONFLICT DO NOTHING
                """
            ),
            params,
        )
        found = await read_me(c, tenant_id, caller.user_id)
    assert found is not None
    return found


ME_SQL = """
    SELECT u.handle, m.role, s.plan_id, s.status
    FROM identity.users u
    JOIN identity.memberships m ON m.user_id = u.id AND m.tenant_id = :t
    LEFT JOIN LATERAL (
        SELECT plan_id, status FROM billing.subscriptions
        WHERE tenant_id = :t AND user_id = u.id
        ORDER BY created_at DESC LIMIT 1
    ) s ON true
    WHERE u.id = :u
"""


async def read_me(c: AsyncConnection, tenant_id: UUID, user_id: UUID) -> MeOut | None:
    row = (await c.execute(text(ME_SQL), {"t": tenant_id, "u": user_id})).first()
    if row is None:
        return None
    return MeOut(
        user_id=user_id,
        handle=row.handle,
        role=Role(row.role),
        plan_id=row.plan_id,
        subscription_status=row.status,
    )


@router.get("/me")
async def get_me(request: Request, caller: Caller, tenant_id: Tenant) -> MeOut:
    """The caller's account, or 403 if `POST /v1/me` hasn't created it yet."""
    async with tenant_tx(request.app.state.engine, tenant_id, DbRole.WORKER) as c:
        found = await read_me(c, tenant_id, caller.user_id)
    if found is None:
        raise HTTPException(403, "no Orqen account yet: call POST /v1/me first")
    return found


# ------------------------------------------------------------------- /v1/submissions


class SubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: UUID
    mode: Mode = Mode.SUBMIT
    kind: Literal["prompt"] = "prompt"  # code submissions need the sandbox (M3)
    prompt: str = Field(min_length=1, max_length=20_000)
    model: str | None = None
    contest_id: UUID | None = None


class SubmissionAccepted(BaseModel):
    submission_id: UUID
    status: SubmissionStatus


@router.post("/submissions", status_code=202)
async def create_submission(
    request: Request,
    response: Response,
    body: SubmissionIn,
    caller: Caller,
    tenant_id: Tenant,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> SubmissionAccepted:
    engine: AsyncEngine = request.app.state.engine
    role = await member_role(engine, tenant_id, caller.user_id)
    trace_id: str = request.state.trace_id
    payload: dict[str, Any] = {"prompt": body.prompt}
    if body.model:
        payload["model"] = body.model
    try:
        async with tenant_tx(engine, tenant_id, DbRole.for_member(role), caller.user_id) as c:
            found = await c.execute(
                text(
                    """
                    INSERT INTO judging.submissions (tenant_id, user_id, problem_id,
                        contest_id, kind, mode, payload, idempotency_key, trace_id)
                    VALUES (:t, :u, :p, :c, :kind, :mode, CAST(:payload AS jsonb), :idem,
                        :trace)
                    RETURNING id
                    """
                ),
                {
                    "t": tenant_id,
                    "u": caller.user_id,
                    "p": body.problem_id,
                    "c": body.contest_id,
                    "kind": body.kind,
                    "mode": body.mode.value,
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "idem": idempotency_key,
                    "trace": trace_id,
                },
            )
            submission_id: UUID = found.scalar_one()
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505" and idempotency_key:
            response.status_code = 200
            return await _replay(engine, tenant_id, role, caller.user_id, idempotency_key)
        if mapped := refusal(exc):
            raise mapped from exc
        raise

    msg = SubmissionMsg(
        tenant_id=tenant_id,
        trace_id=trace_id,
        submission_id=submission_id,
        user_id=caller.user_id,
        problem_id=body.problem_id,
        mode=body.mode,
    )
    lane = streams.SUBMISSIONS_PRIORITY if body.mode is Mode.RUN else streams.SUBMISSIONS
    redis: Redis = request.app.state.redis
    await redis.xadd(lane.name, msg.to_fields())  # type: ignore[arg-type]
    await redis.hset(
        keys.sub_status(tenant_id, submission_id),
        mapping={"status": SubmissionStatus.QUEUED.value, "seq": 0},
    )
    await redis.expire(keys.sub_status(tenant_id, submission_id), keys.TTL_SUBMISSION_STATE_S)
    response.headers["Location"] = f"/v1/submissions/{submission_id}"
    log.info("submission.queued", submission_id=str(submission_id), mode=body.mode.value)
    return SubmissionAccepted(submission_id=submission_id, status=SubmissionStatus.QUEUED)


async def _replay(
    engine: AsyncEngine, tenant_id: UUID, role: Role, user_id: UUID, key: str
) -> SubmissionAccepted:
    async with tenant_tx(engine, tenant_id, DbRole.for_member(role), user_id) as c:
        row = (
            await c.execute(
                text(
                    "SELECT id, status FROM judging.submissions"
                    " WHERE tenant_id = :t AND user_id = :u AND idempotency_key = :k"
                ),
                {"t": tenant_id, "u": user_id, "k": key},
            )
        ).one()
    return SubmissionAccepted(submission_id=row.id, status=SubmissionStatus(row.status))
