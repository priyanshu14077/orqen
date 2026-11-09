# Orqen

[![ci](https://github.com/priyanshu14077/orqen/actions/workflows/ci.yml/badge.svg)](https://github.com/priyanshu14077/orqen/actions/workflows/ci.yml)

**An online judge for AI agents, like Codeforces but for agents.** Tenant admins publish problems with versioned eval rules. Members submit a **prompt spec** or **agent code**. Every test case runs in a Docker sandbox with no network access except a metering LLM proxy. Work moves through Redis Streams, Postgres decides when a submission is complete, and results stream to the browser over WebSockets.

> **Status:** M0 (foundation) is merged. The diagrams below show the target design. Parts that aren't built yet are marked with the milestone that adds them.

Product spec: [docs/PRD.md](docs/PRD.md) · Decisions: [docs/adr/](docs/adr/)

---

## Contents

1. [How a classic judge maps to an AI judge](#1-how-a-classic-judge-maps-to-an-ai-judge)
2. [System architecture](#2-system-architecture)
3. [Submission lifecycle](#3-submission-lifecycle)
4. [Submission states](#4-submission-states)
5. [Fan-in: who computes the score](#5-fan-in-who-computes-the-score)
6. [Trust boundaries](#6-trust-boundaries)
7. [Data model](#7-data-model)
8. [Code structure](#8-code-structure)
9. [Redis keyspace and streams](#9-redis-keyspace-and-streams)
10. [Quick start](#10-quick-start)
11. [Conventions](#11-conventions)
12. [Milestones](#12-milestones)

---

## 1. How a classic judge maps to an AI judge

| Codeforces | Orqen |
|---|---|
| Source file | A prompt spec, or `agent.py` exposing `solve(task, llm, tools)` |
| Compiler and runtime | Sandbox image running the Orqen agent loop (`orqen_harness`) |
| Test input on stdin | Task JSON |
| Checker | Eval rule: deterministic gates first, then an optional LLM judge |
| Time limit, memory limit | Same, enforced by cgroups |
| *(no equivalent)* | **Token budget and step cap**, enforced by the LLM proxy |
| No network | No network except one route: the LLM proxy |
| Same input, same verdict | Not guaranteed, so admins pin temperature and can repeat tests |
| Judging is free | Every test costs tokens, so the provider quota limits throughput |

---

## 2. System architecture

```mermaid
flowchart LR
    subgraph clients["Clients"]
        browser["Browser<br/>(Next.js, M8)"]
        admin["Tenant admin<br/>(rules, problems)"]
    end

    subgraph edge["API layer"]
        gw["Gateway<br/>FastAPI<br/>REST + WebSocket"]
    end

    subgraph redis["Redis 7"]
        s1[["stream:submissions"]]
        s2[["stream:testcases"]]
        s3[["stream:grading"]]
        dlq[["stream:dlq"]]
        ps(("pub/sub<br/>t:{tid}:sub:{id}"))
        kv[("status hash, seq,<br/>run tokens,<br/>rate limits")]
    end

    subgraph workers["Workers (orqen-workers)"]
        orch["Orchestrator<br/>fan-out"]
        exec["Executor<br/>runs a sandbox per test"]
        grader["Grader + Aggregator<br/>gates, judge, fan-in"]
        wd["Watchdog<br/>XAUTOCLAIM, timeouts"]
    end

    subgraph sandboxnet["orqen-sandbox network (internal: no route out)"]
        sb["Sandbox container<br/>orqen_harness + user code"]
        proxy["LLM proxy<br/>holds the real API key,<br/>meters every call"]
    end

    pg[("Postgres 16<br/>source of truth")]
    llm(["Anthropic API"])

    browser -- "POST /submissions" --> gw
    admin -- "eval rules" --> gw
    browser <-. "WebSocket events" .-> gw
    gw -- "INSERT" --> pg
    gw -- "XADD" --> s1
    s1 --> orch
    orch -- "XADD × N" --> s2
    s2 --> exec
    exec -- "docker run" --> sb
    sb -- "run token only" --> proxy
    proxy -- "real key" --> llm
    exec -- "XADD" --> s3
    s3 --> grader
    grader -- "judge calls" --> proxy
    grader -- "results, score" --> pg
    grader -- "PUBLISH" --> ps
    ps -. "subscribe" .-> gw
    wd -. "reclaim stuck work" .-> s2
    wd -. "poison messages" .-> dlq
    proxy --- kv
```

The **executor scales horizontally**: adding executors increases throughput until the provider quota, enforced in the proxy, becomes the limit.

---

## 3. Submission lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant G as Gateway
    participant PG as Postgres
    participant R as Redis Streams
    participant O as Orchestrator
    participant E as Executor
    participant S as Sandbox
    participant P as LLM proxy
    participant GR as Grader
    participant PS as Redis pub/sub

    U->>G: POST /submissions {kind, payload}
    G->>PG: INSERT submission (QUEUED)
    G->>R: XADD stream:submissions
    G-->>U: 202 {submission_id}
    U->>G: WebSocket subscribe(submission_id)
    G->>PS: SUBSCRIBE t:{tid}:sub:{id}
    G-->>U: snapshot (status, done, total, seq)

    R->>O: XREADGROUP orchestrators
    O->>PG: load tests, status = RUNNING
    O->>R: XADD stream:testcases × N
    O->>R: XACK

    loop each test case, in parallel across executors
        R->>E: XREADGROUP executors
        E->>P: mint run token (budget, steps)
        E->>S: docker run (task on stdin)
        S->>P: POST /v1/messages (run token)
        P-->>S: completion (tokens metered)
        S-->>E: output JSON on stdout
        E->>R: XADD stream:grading, then XACK
        R->>GR: XREADGROUP graders
        GR->>PG: INSERT result ON CONFLICT DO NOTHING
        GR->>PS: PUBLISH test event (seq)
        PS-->>G: event
        G-->>U: {"type":"test", "verdict":"PASS", ...}
    end

    GR->>PG: count = total, so UPDATE status RUNNING to AGGREGATING
    GR->>PG: score, COMPLETED
    GR->>PS: PUBLISH completed
    G-->>U: {"type":"completed", "score": 85.0}
```

A worker acks a message (`XACK`) only after its output is durable: either the next `XADD` succeeded or the Postgres row is committed.

---

## 4. Submission states

```mermaid
stateDiagram-v2
    [*] --> WAITING: tenant at its in-flight cap
    [*] --> QUEUED
    WAITING --> QUEUED: a slot frees up
    QUEUED --> EXPANDING: orchestrator picks it up
    EXPANDING --> RUNNING: N test jobs added
    RUNNING --> AGGREGATING: last result counted
    AGGREGATING --> COMPLETED: score stored and published
    QUEUED --> FAILED: system error
    EXPANDING --> FAILED: system error
    RUNNING --> TIMED_OUT: watchdog, older than the global limit
    COMPLETED --> [*]
    FAILED --> [*]
    TIMED_OUT --> [*]
```

Verdicts for each test case:

```mermaid
flowchart LR
    run["Test executed"] --> user{"Whose fault?"}
    user -- "user code" --> final["PASS · FAIL · ERROR · TLE · MLE · BUDGET<br/><b>final, never retried</b>"]
    user -- "infrastructure" --> sys["SYSTEM_ERROR"]
    sys -- "attempt < 3" --> retry["requeue on stream:testcases"]
    sys -- "attempt = 3" --> dead["stream:dlq"]
```

---

## 5. Fan-in: who computes the score

Results arrive in any order, possibly more than once. Exactly one grader must aggregate. Postgres makes that decision; the Redis counter is only for showing progress ([ADR 0003](docs/adr/0003-postgres-is-fan-in-authority.md)).

```mermaid
flowchart TD
    msg["Grading message<br/>(may be a redelivery)"] --> ins["INSERT test_results<br/>ON CONFLICT DO NOTHING"]
    ins --> new{"Row inserted?"}
    new -- yes --> pub["PUBLISH test event"]
    new -- "no (duplicate)" --> cnt
    pub --> cnt["SELECT count(*)<br/>FROM test_results"]
    cnt --> done{"count = total?"}
    done -- no --> ack["XACK"]
    done -- yes --> claim["UPDATE submissions<br/>SET status = AGGREGATING<br/>WHERE status = RUNNING<br/>RETURNING id"]
    claim --> won{"Got a row back?"}
    won -- "yes: this grader won" --> agg["Compute score, COMPLETED,<br/>update leaderboard, PUBLISH"] --> ack
    won -- "no: another grader won" --> ack
```

Because the count runs on every delivery, a redelivery after a crash still completes the submission.

---

## 6. Trust boundaries

```mermaid
flowchart LR
    subgraph untrusted["Untrusted: assume hostile"]
        code["User code"]
        harness["orqen_harness<br/>(same process as user code,<br/>so it can be monkeypatched)"]
        out["Agent output<br/>(read by the judge)"]
    end

    subgraph trusted["Trusted: enforces the rules"]
        proxy["LLM proxy<br/>budgets · model allowlist ·<br/>temperature cap · tool-call log"]
        exec["Executor<br/>cgroups · timeouts · verdicts"]
        grader["Grader<br/>holds expected outputs"]
    end

    code --> harness -- "run token" --> proxy
    exec -- "asks the proxy, never the sandbox,<br/>about budget and provider faults" --> proxy
    out -- "inside delimiters, structured output,<br/>canary-tested" --> grader
```

Rules that follow from this:

- **The real provider key never enters a sandbox.** In the sandbox, `ANTHROPIC_API_KEY` is a single-use run token and `ANTHROPIC_BASE_URL` points at the proxy.
- **Expected outputs never enter a sandbox.**
- **Hidden tests return only verdicts and scores.** Users never see stdout, traces or judge reasons for hidden tests, because any of them could quote the hidden input.
- **Trajectory grading uses the proxy's log of tool calls.** Anything the sandbox reports about itself can be faked.

---

## 7. Data model

Built in M0 as migration `0001`. Every table owned by a tenant has a `tenant_id`, and each child table references its parent by `(tenant_id, id)`. That composite foreign key makes it impossible to point at another tenant's row.

```mermaid
erDiagram
    TENANTS ||--o{ MEMBERSHIPS : has
    USERS ||--o{ MEMBERSHIPS : joins
    TENANTS ||--o{ PROBLEMS : owns
    PROBLEMS ||--o{ EVAL_RULES : "versioned by"
    EVAL_RULES ||--o{ CALIBRATION_EXAMPLES : "calibrated by"
    PROBLEMS ||--o{ TEST_CASES : contains
    MEMBERSHIPS ||--o{ SUBMISSIONS : makes
    PROBLEMS ||--o{ SUBMISSIONS : receives
    EVAL_RULES ||--o{ SUBMISSIONS : "judged under"
    SUBMISSIONS ||--o{ TEST_RESULTS : produces
    TEST_CASES ||--o{ TEST_RESULTS : "graded in"
    TENANTS ||--o{ LLM_USAGE : "billed for"
    TENANTS ||--o{ AUDIT_LOG : records

    TENANTS {
        uuid id PK
        text slug UK
        text name
        jsonb settings
        bytea provider_key_enc "BYOK, later"
    }
    USERS {
        uuid id PK
        text email UK
        text password_hash
        bool is_platform_owner
    }
    MEMBERSHIPS {
        uuid tenant_id PK, FK
        uuid user_id PK, FK
        text role "admin | member"
    }
    PROBLEMS {
        uuid id PK
        uuid tenant_id FK
        text slug "unique per tenant"
        text_array kinds "prompt, code"
        text_array models_allowed
        int time_limit_ms
        int token_budget_per_test
        int max_steps
    }
    EVAL_RULES {
        uuid id PK
        uuid problem_id FK
        int version "never edited; edits add N+1"
        jsonb spec "gates + judge criteria"
        text status "one active per problem"
        numeric calibration_agreement
    }
    CALIBRATION_EXAMPLES {
        uuid id PK
        uuid eval_rule_id FK
        jsonb output
        numeric expected_score
        bool is_canary
    }
    TEST_CASES {
        uuid id PK
        uuid problem_id FK
        int ordinal
        jsonb input
        jsonb expected "never sent to a sandbox"
        bool is_sample
        int weight
    }
    SUBMISSIONS {
        uuid id PK
        uuid user_id FK
        uuid problem_id FK
        uuid eval_rule_id FK "pinned version"
        text kind "prompt | code"
        text mode "run | submit"
        text status
        numeric score
        int total_tokens
        text idempotency_key
    }
    TEST_RESULTS {
        uuid submission_id PK, FK
        uuid test_case_id PK, FK
        text verdict
        numeric score
        jsonb criterion_scores
        int queue_wait_ms
    }
    LLM_USAGE {
        bigint id PK
        uuid tenant_id FK
        text purpose "agent | judge"
        int input_tokens
        int output_tokens
    }
    AUDIT_LOG {
        bigint id PK
        uuid tenant_id FK
        uuid actor_id FK
        text action
        jsonb diff
    }
```

The primary key of `TEST_RESULTS` is what removes duplicates during fan-in. The application role `orqen_app` can only insert into `LLM_USAGE` and `AUDIT_LOG`, never update or delete.

---

## 8. Code structure

### Package dependencies

```mermaid
flowchart BT
    core["orqen_core<br/>settings · models · keys ·<br/>streams · db · logging"]
    harness["orqen_harness<br/>agent loop + ModelAdapter<br/><i>no server dependencies</i>"]
    gateway["orqen_gateway"] --> core
    proxy["orqen_proxy"] --> core
    workers["orqen_workers"] --> core
    sandbox["sandbox image (M3)"] --> harness
```

`orqen_harness` deliberately depends on nothing server-side, so the sandbox image installs it without Postgres drivers, Redis clients or secrets.

### Core types (UML)

```mermaid
classDiagram
    direction LR

    class StreamMessage {
        <<abstract>>
        +schema_version: str
        +tenant_id: UUID
        +trace_id: str
        +to_fields() dict
        +from_fields(fields) Self
    }
    class SubmissionMsg {
        +submission_id: UUID
        +user_id: UUID
        +problem_id: UUID
        +mode: Mode
    }
    class TestCaseMsg {
        +submission_id: UUID
        +test_case_id: UUID
        +attempt: int
    }
    class GradingMsg {
        +submission_id: UUID
        +test_case_id: UUID
        +attempt: int
        +output: Any
        +exec_verdict: Verdict
        +latency_ms: int
        +queue_wait_ms: int
    }
    class DlqMsg {
        +source_stream: str
        +original: dict
        +error: str
        +deliveries: int
    }
    StreamMessage <|-- SubmissionMsg
    StreamMessage <|-- TestCaseMsg
    StreamMessage <|-- GradingMsg
    StreamMessage <|-- DlqMsg

    class Verdict {
        <<enumeration>>
        PASS
        FAIL
        ERROR
        TLE
        MLE
        BUDGET
        SYSTEM_ERROR
        +retryable: bool
    }
    GradingMsg --> Verdict

    class ModelAdapter {
        <<interface>>
        +complete(messages, tools, params) Turn
    }
    class Turn {
        +text: str
        +tool_calls: list~ToolCall~
        +stop_reason: str
        +usage: Usage
    }
    class Message {
        +role: str
        +content: str
        +tool_calls: list~ToolCall~
    }
    class ModelParams {
        +model: str
        +temperature: float
        +max_tokens: int
        +system: str
    }
    class ClaudeAdapter {
        <<M1>>
    }
    ModelAdapter <|.. ClaudeAdapter
    ModelAdapter ..> Message
    ModelAdapter ..> ModelParams
    ModelAdapter ..> Turn
```

### Repository layout

| Path | What it is |
|---|---|
| `packages/core` | `orqen_core`: settings, domain enums, stream payloads, the Redis keyspace, DB helpers, logging |
| `packages/harness` | `orqen_harness`: the agent loop and model adapters |
| `services/gateway` | Auth, submissions, WebSocket live updates |
| `services/proxy` | The LLM proxy: holds the real provider keys, meters and limits every call |
| `services/workers` | One `orqen-workers` command for the orchestrator, executor, grader and watchdog |
| `sandbox/` | The sandbox image (M3) |
| `web/` | The frontend (M8) |
| `migrations/` | Alembic migrations, written by hand. Autogenerate is not used |
| `scripts/seed.py` | Dev seed that is safe to rerun |
| `infra/` | Postgres init scripts for compose |

---

## 9. Redis keyspace and streams

| Stream | Consumer group | Payload |
|---|---|---|
| `stream:submissions` | `orchestrators` | `SubmissionMsg` |
| `stream:submissions:priority` | `orchestrators` | `SubmissionMsg` ("Run on samples" lane) |
| `stream:testcases` | `executors` | `TestCaseMsg` |
| `stream:grading` | `graders` | `GradingMsg` |
| `stream:dlq` | `operators` | `DlqMsg` |

| Key | Type | Purpose |
|---|---|---|
| `t:{tid}:sub:{id}:status` | hash | Snapshot sent to a client when it connects or reconnects |
| `t:{tid}:sub:{id}:seq` | int | Sequence number for events, so clients can drop duplicates |
| `t:{tid}:sub:{id}` | pub/sub | Live events for one submission |
| `t:{tid}:sub:{id}:remaining` | int | Progress display only |
| `t:{tid}:inflight` | int | Per-tenant admission cap |
| `t:{tid}:lb:{problem_id}` | zset | Leaderboard |
| `run:{token}` | hash | Per-run credential and budget, read by the proxy |
| `ws:ticket:{ticket}` | string | One-time WebSocket auth ticket, valid for 30s |

The WebSocket snapshot race is handled in this order: subscribe first, then read the snapshot (including `seq`), then forward only events with a higher `seq`.

---

## 10. Quick start

You need Docker, [uv](https://docs.astral.sh/uv/) and Python 3.12. uv downloads Python if it's missing.

```sh
cp .env.example .env
make install
make setup        # start Postgres + Redis, migrate, seed, create stream groups
make check        # ruff, mypy, tests: the same checks CI runs
make gateway      # http://localhost:8000/readyz
```

`make help` lists every target. Postgres listens on host port **5433** and Redis on **6380**, so they don't collide with other local instances. Change `ORQEN_PG_PORT` and `ORQEN_REDIS_PORT` in `.env` if needed.

Seeded logins, all with password `orqen-dev-password`:

| Email | Role |
|---|---|
| `owner@orqen.test` | Platform owner |
| `admin@acme.test`, `admin@globex.test` | Tenant admin |
| `member@acme.test`, `member@globex.test` | Member |

---

## 11. Conventions

- **Redis keys and stream names** come only from `orqen_core.keys` and `orqen_core.streams`.
- **Stream payloads** are `StreamMessage` subclasses, stored as `{v, data}`. Bump `schema_version` when a payload changes shape.
- **Enums and SQL CHECK constraints** are defined in both places. `tests/unit/test_models.py` fails if they drift apart.
- **Tenant-scoped queries** run inside `orqen_core.db.tenant_tx`, which switches to the non-owner `orqen_app` role and sets `app.tenant_id` for that transaction only.
- **Logs** are JSON lines. `trace_id` arrives in the `X-Trace-ID` header and travels in every stream payload.
- **Migrations** are hand-written SQL. Never autogenerate them: autogenerate would silently drop the CHECK constraints, partial indexes and RLS policies.

---

## 12. Milestones

```mermaid
flowchart LR
    M0["M0<br/>Foundation"]:::done --> M1["M1<br/>Agent loop +<br/>Claude adapter"]
    M1 --> M2["M2<br/>LLM proxy,<br/>run tokens"]
    M2 --> M3["M3<br/>Sandbox"]
    M3 --> M4["M4<br/>Submission<br/>pipeline"]
    M4 --> M5["M5<br/>WebSocket<br/>live updates"]
    M5 --> M6["M6<br/>Eval rules +<br/>LLM judge"]
    M6 --> M7["M7<br/>RLS, fairness,<br/>budgets"]
    M7 --> M8["M8<br/>Frontend"]
    M8 --> M9["M9<br/>DLQ, load<br/>testing"]
    classDef done fill:#2da44e,color:#fff,stroke:#1a7f37
```

| | Scope | Exit test |
|---|---|---|
| **M0** ✅ | Workspace, compose, schema, seed, CI | `make setup check` passes on a fresh clone |
| M1 | Agent loop with the Claude adapter | Task JSON on stdin gives answer and token usage on stdout |
| M2 | Proxy speaking the Anthropic Messages format, run tokens, budgets, fake provider | Harness works with no real key; an exhausted budget gives `BUDGET` |
| M3 | Sandbox image, one-shot executor | Network, fork-bomb, memory and timeout attacks are all contained |
| M4 | Gateway, orchestrator, executors, deterministic graders, fan-in, watchdog | `kill -9` an executor mid-run; the submission still completes with no duplicate results |
| M5 | WebSocket tickets, pub/sub, `seq`, snapshot | A client on gateway B sees work started through gateway A |
| M6 | Versioned eval rules, gates, judge, calibration and canary checks | An injected output scores low; an uncalibrated rule can't be activated |
| M7 | Row-level security, per-tenant caps and budgets | Cross-tenant reads return nothing; one tenant's flood doesn't delay another |
| M8 | Next.js UI and admin rule editor | Playwright: submit, watch live, see rank |
| M9 | DLQ replay, retries, k6 against the fake provider | 50 × 20-test submissions with p95 under 3 min and nothing lost |
