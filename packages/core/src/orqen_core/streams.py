"""Stream names, their consumer groups, and the bootstrap that creates the groups.

Streams are shared by all tenants; every payload carries `tenant_id`.
"""

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import ResponseError


@dataclass(frozen=True)
class Stream:
    name: str
    group: str


SUBMISSIONS = Stream("stream:submissions", "orchestrators")
SUBMISSIONS_PRIORITY = Stream("stream:submissions:priority", "orchestrators")
TESTCASES = Stream("stream:testcases", "executors")
GRADING = Stream("stream:grading", "graders")
DLQ = Stream("stream:dlq", "operators")

ALL: tuple[Stream, ...] = (SUBMISSIONS, SUBMISSIONS_PRIORITY, TESTCASES, GRADING, DLQ)


async def ensure_groups(redis: Redis) -> list[Stream]:
    """Create every stream and consumer group that doesn't exist yet. Safe to rerun.

    Groups start at id `0`, not `$`, so a group created after messages were already
    added still delivers them. Returns the groups that were created.
    """
    created = []
    for stream in ALL:
        try:
            await redis.xgroup_create(stream.name, stream.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        else:
            created.append(stream)
    return created
