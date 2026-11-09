# ADR 0003: Postgres decides when a submission is complete

**Status:** accepted · 2026-11-09 · replaces PRD §7.3

## Context

N test results arrive at graders in any order, possibly more than once. Exactly one
grader must compute the final score.

Both earlier designs write to two systems in sequence: `HSETNX` then `HINCRBY`
(pasted plan), or `INSERT` then `DECR` (PRD §7.3). If a grader crashes between the two
writes, the counter never reaches zero. Redelivery doesn't help: the second write is
skipped because the first one already happened.

## Decision

```
INSERT INTO test_results ... ON CONFLICT (submission_id, test_case_id) DO NOTHING
  -- if a row was inserted: PUBLISH the test event
done = SELECT count(*) FROM test_results WHERE submission_id = $1
if done == total:
    UPDATE submissions SET status = 'AGGREGATING'
     WHERE id = $1 AND status = 'RUNNING' RETURNING id
    -- only the grader that gets a row back aggregates
XACK
```

The count runs on every delivery, including duplicates, so a redelivered message
after a crash still completes the submission. The conditional `UPDATE` lets exactly
one grader win.

`t:{tid}:sub:{id}:remaining` in Redis stays, for cheap progress display only.

## Consequences

One extra `count(*)` per result, served by the primary key index. Completion no longer
depends on Redis being consistent with Postgres.
