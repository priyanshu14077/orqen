"""Orchestrator: turns one submission into one job per test case.

A `run` submission gets the sample tests, a `submit` gets all of them. The status moves
QUEUED → EXPANDING → RUNNING (with `total_tests`), each step published as an event,
and the test jobs are added after RUNNING commits, because executors skip tests of a
submission that isn't RUNNING. A redelivered submission that is still RUNNING adds its jobs again;
executors skip tests that already have a result, and the grader drops duplicates.
"""

from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core import keys, streams
from orqen_core.db import DbRole, tenant_tx
from orqen_core.logging import get_logger
from orqen_core.models import SubmissionMsg, SubmissionStatus, TestCaseMsg
from orqen_workers import events
from orqen_workers.consumer import Fields, Poison

log = get_logger(__name__)

LIVE = (SubmissionStatus.QUEUED, SubmissionStatus.EXPANDING, SubmissionStatus.RUNNING)


class Orchestrator:
    def __init__(self, engine: AsyncEngine, redis: Redis) -> None:
        self.engine = engine
        self.redis = redis

    async def handle(self, msg_id: str, fields: Fields) -> None:
        msg = SubmissionMsg.from_fields(fields)
        sub = msg.submission_id
        async with tenant_tx(self.engine, msg.tenant_id, DbRole.WORKER) as c:
            row = (
                await c.execute(
                    text(
                        """
                        SELECT s.status, s.mode, s.problem_id, p.time_limit_ms, p.mem_limit_mb,
                               p.token_budget_per_test, p.max_steps
                        FROM judging.submissions s
                        JOIN authoring.problems p ON p.id = s.problem_id
                        WHERE s.id = :id FOR UPDATE OF s
                        """
                    ),
                    {"id": sub},
                )
            ).first()
            if row is None:
                raise Poison(f"submission {sub} not found")
            if row.status not in LIVE:
                return
            tests = (
                await c.execute(
                    text(
                        "SELECT id, is_sample FROM authoring.test_cases WHERE problem_id = :p"
                        " AND (is_sample OR :all) ORDER BY ordinal"
                    ),
                    {"p": row.problem_id, "all": row.mode == "submit"},
                )
            ).all()
            if row.status == SubmissionStatus.QUEUED:
                await c.execute(
                    text(
                        "UPDATE judging.submissions SET status = 'EXPANDING',"
                        " started_at = now() WHERE id = :id"
                    ),
                    {"id": sub},
                )
        if row.status == SubmissionStatus.QUEUED:
            await self._say(msg, {"type": "status", "status": "EXPANDING"}, {"status": "EXPANDING"})

        samples = sum(1 for t in tests if t.is_sample)
        status = SubmissionStatus.RUNNING if tests else SubmissionStatus.FAILED
        async with tenant_tx(self.engine, msg.tenant_id, DbRole.WORKER) as c:
            await c.execute(
                text(
                    "UPDATE judging.submissions SET status = :st, total_tests = :n,"
                    " completed_at = CASE WHEN :failed THEN now() END"
                    " WHERE id = :id AND status IN ('EXPANDING', 'RUNNING')"
                ),
                {"st": status.value, "n": len(tests), "failed": not tests, "id": sub},
            )
        await self._say(
            msg,
            {
                "type": "meta",
                "text": f"expand  {len(tests)} tests ({samples} sample,"
                f" {len(tests) - samples} hidden)",
            },
        )
        await self._say(
            msg,
            {
                "type": "meta",
                "text": f"expand  limits {row.time_limit_ms / 1000:g} s · {row.mem_limit_mb} MB"
                f" · {row.token_budget_per_test:,} tok · {row.max_steps} steps",
            },
        )
        for test in tests:
            job = TestCaseMsg(
                tenant_id=msg.tenant_id,
                trace_id=msg.trace_id,
                submission_id=sub,
                test_case_id=test.id,
            )
            await self.redis.xadd(streams.TESTCASES.name, job.to_fields())  # type: ignore[arg-type]
        await self.redis.set(
            keys.sub_remaining(msg.tenant_id, sub), len(tests), ex=keys.TTL_SUBMISSION_STATE_S
        )
        await self._say(
            msg,
            {"type": "status", "status": status.value, "total": len(tests)},
            {"status": status.value, "done": 0, "total": len(tests)},
        )
        log.info(
            "orchestrator.expanded", submission_id=str(sub), tests=len(tests), trace_id=msg.trace_id
        )

    async def _say(
        self,
        msg: SubmissionMsg,
        event: dict[str, Any],
        snapshot: dict[str, str | int | float] | None = None,
    ) -> None:
        await events.publish(self.redis, msg.tenant_id, msg.submission_id, event, snapshot)
