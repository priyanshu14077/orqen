"""Live judging: the event snapshot and the Server-Sent Events stream.

    GET /v1/submissions/{id}/events?after=<seq>    text/event-stream

The stream follows the snapshot protocol: subscribe to the submission's channel first,
then replay the stored event list from `after`, then forward live events with a higher
`seq`. Nothing is missed between the replay and the subscription, and duplicates are
dropped by `seq`. The stream ends after the `completed` event, or after
`MAX_STREAM_S`; the client reconnects with the last `seq` it applied.

Every event passes `public_event`, an allow-list per event type. It is the server's
redaction contract: whatever a worker publishes, only these fields reach a browser.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import text

from orqen_core import keys
from orqen_gateway.deps import AsMember, Member

router = APIRouter(prefix="/v1")

COMMON = {"seq", "ts", "type", "submission_id"}
ALLOWED: dict[str, set[str]] = {
    "meta": COMMON | {"text"},
    "status": COMMON | {"status", "total"},
    "test": COMMON
    | {
        "test",
        "test_case_id",
        "kind",
        "attempt",
        "max_attempts",
        "verdict",
        "score",
        "tokens",
        "steps",
        "latency_ms",
        "detail",
    },
    "completed": COMMON | {"status", "score", "passed", "total", "tokens"},
}
TERMINAL = {"COMPLETED", "FAILED", "TIMED_OUT"}
MAX_STREAM_S = 600
KEEPALIVE_S = 15


def public_event(event: dict[str, Any]) -> dict[str, Any] | None:
    allowed = ALLOWED.get(str(event.get("type")))
    if allowed is None:
        return None
    return {k: v for k, v in event.items() if k in allowed}


async def stored_events(redis: Redis, tenant_id: UUID, submission_id: UUID) -> list[dict[str, Any]]:
    raw = await redis.lrange(keys.sub_events(tenant_id, submission_id), 0, -1)
    events = [e for e in (public_event(json.loads(r)) for r in raw) if e is not None]
    return sorted(events, key=lambda e: int(e["seq"]))


async def visible_status(request: Request, who: Member, submission_id: UUID) -> str:
    """The submission's status, or 404 when row-level security hides it from the caller."""
    async with who.tx(request.app.state.engine) as c:
        status = (
            await c.execute(
                text("SELECT status FROM judging.submissions WHERE id = :id"),
                {"id": submission_id},
            )
        ).scalar_one_or_none()
    if status is None:
        raise HTTPException(404, "submission not found")
    return str(status)


def frame(event: dict[str, Any]) -> str:
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.get("/submissions/{submission_id}/events")
async def stream_events(
    request: Request,
    submission_id: UUID,
    who: AsMember,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    status = await visible_status(request, who, submission_id)
    if last_event_id and last_event_id.isdigit():
        after = max(after, int(last_event_id))
    redis: Redis = request.app.state.redis

    async def events() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(keys.sub_channel(who.tenant_id, submission_id))
        last = after
        deadline = time.monotonic() + MAX_STREAM_S
        try:
            yield "retry: 2000\n\n"
            for event in await stored_events(redis, who.tenant_id, submission_id):
                if event["seq"] > last:
                    last = event["seq"]
                    yield frame(event)
                    if event["type"] == "completed":
                        return
            if status in TERMINAL:
                return
            while time.monotonic() < deadline:
                if await request.is_disconnected():
                    return
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=KEEPALIVE_S)
                if msg is None:
                    yield ": keepalive\n\n"
                    continue
                live = public_event(json.loads(msg["data"]))
                if live is None or live["seq"] <= last:
                    continue
                last = live["seq"]
                yield frame(live)
                if live["type"] == "completed":
                    return
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
