"""Live progress for one submission: an event log, a status snapshot and pub/sub.

Every event gets the next `seq` and is appended to the submission's event list as it
is published, so a client that missed a pub/sub message can replay the list. Two
workers can append out of order; readers sort by `seq`. Postgres still holds the
real state; these exist to show progress.

Event shapes (all carry `seq`, `ts` and `submission_id`):

    meta       {"text"}                                       log preamble lines
    status     {"status", "total"?}                           stage changes
    test       {"test", "test_case_id", "kind", "attempt", "max_attempts", "verdict",
                "score", "tokens", "steps", "latency_ms", "detail"}
    completed  {"status", "score", "passed", "total", "tokens"}

Events never carry outputs, traces or expected values, so hidden tests stay redacted.
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from orqen_core import keys


async def publish(
    redis: Redis,
    tenant_id: UUID,
    submission_id: UUID,
    event: dict[str, Any],
    snapshot: dict[str, str | int | float] | None = None,
) -> int:
    """Publish `event` with the next `seq`, and merge `snapshot` into the status hash."""
    seq = int(await redis.incr(keys.sub_seq(tenant_id, submission_id)))
    body = json.dumps(
        {
            "seq": seq,
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "submission_id": str(submission_id),
            **event,
        }
    )
    status_key = keys.sub_status(tenant_id, submission_id)
    events_key = keys.sub_events(tenant_id, submission_id)
    async with redis.pipeline(transaction=False) as pipe:
        mapping: dict[Any, Any] = {**(snapshot or {}), "seq": seq}
        pipe.hset(status_key, mapping=mapping)
        pipe.rpush(events_key, body)
        for key in (status_key, events_key, keys.sub_seq(tenant_id, submission_id)):
            pipe.expire(key, keys.TTL_SUBMISSION_STATE_S)
        pipe.publish(keys.sub_channel(tenant_id, submission_id), body)
        await pipe.execute()
    return seq
