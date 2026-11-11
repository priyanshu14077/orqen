"""Grader: scores one test output and, after the last one, the whole submission.

Two transactions per message, in this order:

1. Grade and `INSERT ... ON CONFLICT DO NOTHING`, then commit. A redelivered message
   inserts nothing.
2. Count the results and, if the count equals `total_tests`, move the submission from
   RUNNING to AGGREGATING. Only the grader whose UPDATE returns a row aggregates: it
   computes the weighted score (0 to 100), sets COMPLETED and updates the practice
   leaderboard in the same transaction.

The count runs after step 1 commits, so whichever grader commits the last result
sees every row. A crash between the steps is repaired by redelivery, because step 2
runs on every delivery, duplicates included.
"""

import json
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core import keys
from orqen_core.db import DbRole, tenant_tx
from orqen_core.logging import get_logger
from orqen_core.models import GradingMsg, SubmissionStatus, Verdict
from orqen_workers import events
from orqen_workers.consumer import Fields, Poison
from orqen_workers.executor import MAX_ATTEMPTS
from orqen_workers.grading import Grade, UnsupportedRule, grade

log = get_logger(__name__)


def detail(result: Grade, error: str | None) -> str:
    """A one-line, judge-authored note for the log. Never quotes the output, because
    hidden-test outputs are secret."""
    if error:
        return error[:200]
    failed = [name.split(":", 1)[1] for name, ok in result.criteria.items() if not ok]
    return f"failed {', '.join(failed)}" if failed else ""


def score_output(spec: dict[str, Any], msg: GradingMsg, expected: Any) -> tuple[Grade, str | None]:
    if msg.exec_verdict is not None:
        return Grade(msg.exec_verdict, 0.0, {}), msg.error
    try:
        return grade(spec, msg.output, expected), None
    except UnsupportedRule as exc:
        return Grade(Verdict.SYSTEM_ERROR, 0.0, {}), f"unsupported eval rule: {exc}"


class Grader:
    def __init__(self, engine: AsyncEngine, redis: Redis) -> None:
        self.engine = engine
        self.redis = redis

    async def handle(self, msg_id: str, fields: Fields) -> None:
        msg = GradingMsg.from_fields(fields)
        async with tenant_tx(self.engine, msg.tenant_id, DbRole.WORKER) as c:
            row = (
                await c.execute(
                    text(
                        """
                        SELECT r.spec, tc.expected, tc.ordinal, tc.is_sample
                        FROM judging.submissions s
                        JOIN authoring.eval_rules r ON r.id = s.eval_rule_id
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
            result, error = score_output(row.spec, msg, row.expected)
            inserted = (
                await c.execute(
                    text(
                        """
                        INSERT INTO judging.test_results (submission_id, test_case_id,
                            tenant_id, verdict, score, output, criterion_scores, error_msg,
                            latency_ms, queue_wait_ms, tokens, steps, attempts)
                        VALUES (:s, :tc, :t, :verdict, :score, CAST(:output AS jsonb),
                            CAST(:criteria AS jsonb), :error, :latency, :wait, :tokens,
                            :steps, :attempt)
                        ON CONFLICT (submission_id, test_case_id) DO NOTHING
                        RETURNING verdict
                        """
                    ),
                    {
                        "s": msg.submission_id,
                        "tc": msg.test_case_id,
                        "t": msg.tenant_id,
                        "verdict": result.verdict.value,
                        "score": result.score,
                        "output": json.dumps(msg.output),
                        "criteria": json.dumps(result.criteria),
                        "error": error,
                        "latency": msg.latency_ms,
                        "wait": msg.queue_wait_ms,
                        "tokens": msg.tokens,
                        "steps": msg.steps,
                        "attempt": msg.attempt,
                    },
                )
            ).first()

        if inserted:
            remaining = await self.redis.decr(keys.sub_remaining(msg.tenant_id, msg.submission_id))
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
                    "verdict": result.verdict.value,
                    "score": result.score,
                    "tokens": msg.tokens,
                    "steps": msg.steps,
                    "latency_ms": msg.latency_ms,
                    "detail": detail(result, error),
                },
                {"remaining": max(int(remaining), 0)},
            )

        async with tenant_tx(self.engine, msg.tenant_id, DbRole.WORKER) as c:
            final = await self._aggregate(c, msg)
        if final is not None:
            await events.publish(
                self.redis,
                msg.tenant_id,
                msg.submission_id,
                {"type": "completed", "status": SubmissionStatus.COMPLETED.value, **final},
                {"status": SubmissionStatus.COMPLETED.value, "score": str(final["score"])},
            )
            log.info(
                "grader.completed",
                submission_id=str(msg.submission_id),
                score=final["score"],
                trace_id=msg.trace_id,
            )

    async def _aggregate(self, c: AsyncConnection, msg: GradingMsg) -> dict[str, Any] | None:
        """Claim and finish the submission if every result is in. None if not this grader."""
        claimed = (
            await c.execute(
                text(
                    """
                    UPDATE judging.submissions s SET status = 'AGGREGATING'
                    WHERE s.id = :s AND s.status = 'RUNNING'
                      AND s.total_tests = (SELECT count(*) FROM judging.test_results r
                                           WHERE r.submission_id = s.id)
                    RETURNING s.tenant_id, s.user_id, s.problem_id, s.mode, s.contest_id,
                              s.ranked
                    """
                ),
                {"s": msg.submission_id},
            )
        ).first()
        if claimed is None:
            return None
        totals = (
            await c.execute(
                text(
                    """
                    SELECT round(100 * sum(tc.weight * coalesce(r.score, 0))
                                 / sum(tc.weight), 3) AS score,
                           coalesce(sum(r.tokens), 0) AS tokens,
                           count(*) FILTER (WHERE r.verdict = 'PASS') AS passed,
                           count(*) AS total,
                           (SELECT coalesce(sum(u.cost_usd), 0) FROM ops.llm_usage u
                            WHERE u.submission_id = :s) AS cost
                    FROM judging.test_results r
                    JOIN authoring.test_cases tc ON tc.id = r.test_case_id
                    WHERE r.submission_id = :s
                    """
                ),
                {"s": msg.submission_id},
            )
        ).one()
        await c.execute(
            text(
                "UPDATE judging.submissions SET status = 'COMPLETED', score = :score,"
                " total_tokens = :tokens, cost_usd = :cost, completed_at = now()"
                " WHERE id = :s"
            ),
            {
                "s": msg.submission_id,
                "score": totals.score,
                "tokens": totals.tokens,
                "cost": totals.cost,
            },
        )
        if claimed.mode == "submit" and claimed.contest_id is None and claimed.ranked:
            await c.execute(
                text(
                    """
                    INSERT INTO competition.practice_bests
                        (tenant_id, problem_id, user_id, best_score, submission_id, reached_at)
                    VALUES (:t, :p, :u, :score, :s, now())
                    ON CONFLICT (problem_id, user_id) DO UPDATE
                    SET best_score = EXCLUDED.best_score,
                        submission_id = EXCLUDED.submission_id,
                        reached_at = EXCLUDED.reached_at
                    WHERE competition.practice_bests.best_score < EXCLUDED.best_score
                    """
                ),
                {
                    "t": claimed.tenant_id,
                    "p": claimed.problem_id,
                    "u": claimed.user_id,
                    "score": totals.score,
                    "s": msg.submission_id,
                },
            )
        return {
            "score": float(totals.score),
            "passed": totals.passed,
            "total": totals.total,
            "tokens": totals.tokens,
        }
