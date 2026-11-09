# ADR 0001: Redis Streams for work queues, pub/sub for live events

**Status:** accepted · 2026-11-09

## Context

Submissions fan out into one job per test case, pass through execution and grading,
and fan back in. Workers crash. A job popped and then lost is a submission that never
finishes.

## Decision

- Work moves on **Redis Streams with consumer groups**: `stream:submissions`,
  `stream:testcases`, `stream:grading`, `stream:dlq`. Names live in `orqen_core.streams`.
- Streams are **shared by all tenants**; every payload carries `tenant_id`.
- Workers `XACK` only after their output is durable (the next `XADD` succeeded or the
  Postgres row committed).
- Groups are created at id `0`, so a group created late still receives earlier entries.
- Live progress uses **pub/sub**, which is allowed to drop messages because Postgres
  and the status hash are the source of truth.

## Why not the alternatives

- **Lists (`LPUSH`/`BRPOP`)**: a popped message is gone; a crash loses it. Streams keep
  it in the pending entries list until acked, with a delivery count for retry limits.
- **Kafka**: partitions, retention and a second piece of infrastructure buy nothing at
  this scale. Redis is already needed for counters, rate limits and pub/sub.
- **Per-tenant streams**: a worker would read N streams, and fairness would still need
  logic. Fairness is handled by admission caps instead (M7).

## Consequences

Delivery is at least once, so every consumer must be idempotent. Redis runs with AOF
(`appendfsync everysec`) so a restart doesn't drop unacked entries.
