"""Executor: runs the harness for one test case and hands the output to the grader.

For each test job the executor mints a run token, starts `python -m orqen_harness` as
a subprocess with the task on stdin, and waits up to the problem's time limit. The
subprocess gets a bare environment, so no secret of the executor's reaches it. M3
replaces the subprocess with the sandbox container behind the same `run_harness`.

Verdicts decided here: TLE (time limit), BUDGET (proxy refused for budget) and ERROR
(no usable answer). Infrastructure faults are retried as a new job up to
`MAX_ATTEMPTS`, then recorded as SYSTEM_ERROR.
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core import runs, streams
from orqen_core.db import DbRole, tenant_tx
from orqen_core.logging import get_logger
from orqen_core.models import GradingMsg, SubmissionStatus, TestCaseMsg, Verdict
from orqen_core.runs import RunGrant
from orqen_harness.protocol import Result, ResultStatus, Task
from orqen_workers import events
from orqen_workers.consumer import Fields, Poison, queue_wait_ms

log = get_logger(__name__)

MAX_ATTEMPTS = 3
TOKEN_GRACE_S = 60


@dataclass(frozen=True)
class Outcome:
    """What one harness run produced: a result, or the verdict that replaces one."""

    result: Result | None
    verdict: Verdict | None = None
    error: str | None = None

    @property
    def infrastructure_fault(self) -> bool:
        return self.verdict is Verdict.SYSTEM_ERROR


def sandbox_env() -> dict[str, str]:
    """The harness's whole environment. Nothing from the executor's own env leaks in."""
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONUNBUFFERED": "1"}


async def run_harness(task: Task, timeout_s: float) -> Outcome:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "orqen_harness",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=sandbox_env(),
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(task.model_dump_json().encode()), timeout_s
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return Outcome(None, Verdict.TLE, f"time limit of {timeout_s:g}s exceeded")
    if proc.returncode != 0:
        tail = err.decode(errors="replace").strip().splitlines()[-1:] or [""]
        return Outcome(None, Verdict.SYSTEM_ERROR, f"harness exited {proc.returncode}: {tail[0]}")
    try:
        result = Result.model_validate_json(out)
    except ValidationError:
        return Outcome(None, Verdict.SYSTEM_ERROR, "harness wrote no valid result")
    match result.status:
        case ResultStatus.OK:
            return Outcome(result)
        case ResultStatus.BUDGET:
            return Outcome(result, Verdict.BUDGET, result.error)
        case ResultStatus.PROVIDER_ERROR:
            return Outcome(result, Verdict.SYSTEM_ERROR, result.error)
        case _:
            return Outcome(result, Verdict.ERROR, result.error)


def pick_model(payload: dict[str, Any], allowed: list[str]) -> str:
    wanted = payload.get("model")
    return wanted if wanted in allowed else allowed[0]


class Executor:
    def __init__(self, engine: AsyncEngine, redis: Redis, proxy_url: str) -> None:
        self.engine = engine
        self.redis = redis
        self.proxy_url = proxy_url

    async def handle(self, msg_id: str, fields: Fields) -> None:
        msg = TestCaseMsg.from_fields(fields)
        waited = queue_wait_ms(msg_id)
        async with tenant_tx(self.engine, msg.tenant_id, DbRole.WORKER) as c:
            row = (
                await c.execute(
                    text(
                        """
                        SELECT s.status, s.user_id, s.payload, p.models_allowed, p.max_steps,
                               p.token_budget_per_test, p.time_limit_ms, tc.input,
                               tc.ordinal, tc.is_sample,
                               EXISTS (SELECT FROM judging.test_results r
                                       WHERE r.submission_id = s.id
                                         AND r.test_case_id = tc.id) AS done
                        FROM judging.submissions s
                        JOIN authoring.problems p ON p.id = s.problem_id
                        JOIN authoring.test_cases tc
                          ON tc.id = :tc AND tc.problem_id = s.problem_id
                        WHERE s.id = :s
                        """
                    ),
                    {"s": msg.submission_id, "tc": msg.test_case_id},
                )
            ).first()
        if row is None:
            raise Poison(f"test {msg.test_case_id} of {msg.submission_id} not found")
        if row.done or row.status != SubmissionStatus.RUNNING:
            return

        grant = RunGrant(
            tenant_id=msg.tenant_id,
            user_id=row.user_id,
            submission_id=msg.submission_id,
            test_case_id=msg.test_case_id,
            models=tuple(row.models_allowed),
            budget_tokens=row.token_budget_per_test,
        )
        timeout_s = row.time_limit_ms / 1000
        token = await runs.mint(self.redis, grant, ttl_s=int(timeout_s) + TOKEN_GRACE_S)
        task = Task(
            proxy_url=self.proxy_url,
            run_token=token,
            model=pick_model(row.payload, row.models_allowed),
            system=row.payload.get("prompt", ""),
            input=row.input,
            max_steps=row.max_steps,
        )
        started = time.monotonic()
        try:
            outcome = await run_harness(task, timeout_s)
        finally:
            await runs.revoke(self.redis, token)
        latency_ms = int((time.monotonic() - started) * 1000)

        if outcome.infrastructure_fault and msg.attempt < MAX_ATTEMPTS:
            retry = msg.model_copy(update={"attempt": msg.attempt + 1})
            await self.redis.xadd(streams.TESTCASES.name, retry.to_fields())  # type: ignore[arg-type]
            # One log row per attempt: the client shows the failed try, then the re-run.
            await events.publish(
                self.redis,
                msg.tenant_id,
                msg.submission_id,
                {
                    "type": "test",
                    "test": row.ordinal,
                    "test_case_id": str(msg.test_case_id),
                    "kind": "sample" if row.is_sample else "hidden",
                    "attempt": msg.attempt,
                    "max_attempts": MAX_ATTEMPTS,
                    "verdict": Verdict.SYSTEM_ERROR.value,
                    "score": None,
                    "tokens": 0,
                    "steps": 0,
                    "latency_ms": latency_ms,
                    "detail": f"{outcome.error or 'infrastructure fault'} · re-queued",
                },
            )
            log.warning(
                "executor.retry",
                submission_id=str(msg.submission_id),
                test_case_id=str(msg.test_case_id),
                attempt=retry.attempt,
                error=outcome.error,
            )
            return

        result = outcome.result
        graded = GradingMsg(
            tenant_id=msg.tenant_id,
            trace_id=msg.trace_id,
            submission_id=msg.submission_id,
            test_case_id=msg.test_case_id,
            attempt=msg.attempt,
            output=result.output if result else None,
            exec_verdict=outcome.verdict,
            error=outcome.error,
            latency_ms=latency_ms,
            queue_wait_ms=waited,
            tokens=(result.usage.input_tokens + result.usage.output_tokens) if result else 0,
            steps=result.steps if result else 0,
        )
        await self.redis.xadd(streams.GRADING.name, graded.to_fields())  # type: ignore[arg-type]
        log.info(
            "executor.ran",
            submission_id=str(msg.submission_id),
            test_case_id=str(msg.test_case_id),
            verdict=outcome.verdict,
            latency_ms=latency_ms,
            trace_id=msg.trace_id,
        )
