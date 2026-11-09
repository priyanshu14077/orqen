# Orqen

A multi-tenant online judge for AI agents. Tenant admins publish problems with
versioned eval rules; members submit a **prompt spec** or **agent code**; every test
case runs in a network-isolated Docker sandbox whose only way out is a metering LLM
proxy. Work moves through Redis Streams, Postgres decides when a submission is
complete, and results stream to the browser over WebSockets.

The product spec is [docs/PRD.md](docs/PRD.md); design decisions are in [docs/adr/](docs/adr/).

## Quick start

Needs Docker, [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv fetches it if missing).

```sh
cp .env.example .env
make install
make setup        # start Postgres + Redis, migrate, seed, create stream groups
make test         # unit + integration
make gateway      # http://localhost:8000/readyz
```

`make help` lists every target. Postgres listens on host port 5433 and Redis on 6380
so they don't collide with other local instances; change `ORQEN_PG_PORT` and
`ORQEN_REDIS_PORT` in `.env` if needed.

Seeded logins (password `orqen-dev-password`): `owner@orqen.test` (platform owner),
`admin@acme.test`, `member@acme.test`, `admin@globex.test`, `member@globex.test`.

## Layout

| Path | What it is |
|---|---|
| `packages/core` | `orqen_core`: settings, domain enums, stream payloads, the Redis keyspace, DB helpers, logging |
| `packages/harness` | `orqen_harness`: the agent loop and model adapters. Runs inside the sandbox, so it depends on nothing server-side |
| `services/gateway` | Auth, submissions, WebSocket live updates |
| `services/proxy` | The LLM proxy: holds the real provider keys, meters and limits every call |
| `services/workers` | One `orqen-workers` binary: orchestrator, executor, grader, watchdog |
| `sandbox/` | The sandbox image (M3) |
| `web/` | The frontend (M8) |
| `migrations/` | Hand-written Alembic migrations. Autogenerate is not used |
| `scripts/seed.py` | Idempotent dev seed |

## Conventions

- **Redis keys and stream names** come only from `orqen_core.keys` and `orqen_core.streams`.
  Tenant-owned keys start with `t:{tenant_id}:`.
- **Stream payloads** are `orqen_core.models.StreamMessage` subclasses, stored as
  `{v, data}`. Bump `schema_version` when a payload changes shape.
- **Enums and SQL CHECKs** are written twice; `tests/unit/test_models.py` fails if they drift.
- **Tenant-scoped queries** run inside `orqen_core.db.tenant_tx`, which switches to the
  non-owner `orqen_app` role and sets `app.tenant_id` for the transaction.
- **Logs** are JSON lines; `trace_id` arrives in `X-Trace-ID` and travels in every stream payload.

## Milestones

| | |
|---|---|
| **M0** | Skeleton: workspace, compose, schema, seed, CI ← *here* |
| M1 | Agent loop + Claude adapter |
| M2 | LLM proxy, run tokens, budgets, fake provider |
| M3 | Sandbox image and one-shot executor |
| M4 | Submission pipeline with deterministic graders |
| M5 | WebSocket live updates over pub/sub |
| M6 | Admin eval rules and the LLM judge |
| M7 | Row-level security, per-tenant fairness and budgets |
| M8 | Frontend |
| M9 | DLQ, retries, load testing |
