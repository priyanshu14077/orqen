"""The Redis keyspace. Every key is built here; no service writes a key string inline.

Tenant-owned keys carry a `t:{tenant_id}:` prefix so a tenant's state can be found,
inspected and expired as a unit.
"""

from uuid import UUID

TTL_SUBMISSION_STATE_S = 3600
TTL_IDEMPOTENCY_S = 86_400
TTL_WS_TICKET_S = 30


def _t(tenant_id: UUID) -> str:
    return f"t:{tenant_id}"


def sub_status(tenant_id: UUID, submission_id: UUID) -> str:
    """Hash: status snapshot for reconnecting clients (status, done, total, seq)."""
    return f"{_t(tenant_id)}:sub:{submission_id}:status"


def sub_remaining(tenant_id: UUID, submission_id: UUID) -> str:
    """Int: tests still to grade. Progress display only; Postgres decides completion."""
    return f"{_t(tenant_id)}:sub:{submission_id}:remaining"


def sub_seq(tenant_id: UUID, submission_id: UUID) -> str:
    """Int: monotonically increasing event sequence for one submission."""
    return f"{_t(tenant_id)}:sub:{submission_id}:seq"


def sub_channel(tenant_id: UUID, submission_id: UUID) -> str:
    """Pub/sub channel carrying live events for one submission."""
    return f"{_t(tenant_id)}:sub:{submission_id}"


def tenant_inflight(tenant_id: UUID) -> str:
    """Int: submissions currently admitted to the pipeline for this tenant."""
    return f"{_t(tenant_id)}:inflight"


def idempotency(tenant_id: UUID, user_id: UUID, key: str) -> str:
    return f"{_t(tenant_id)}:idem:{user_id}:{key}"


def leaderboard(tenant_id: UUID, problem_id: UUID) -> str:
    return f"{_t(tenant_id)}:lb:{problem_id}"


def run_token(token: str) -> str:
    """Hash: per-run sandbox credential and budget. Not tenant-prefixed because the
    proxy only knows the token; the hash itself records the tenant."""
    return f"run:{token}"


def ws_ticket(ticket: str) -> str:
    return f"ws:ticket:{ticket}"


def rate_limit_provider(provider: str) -> str:
    return f"rl:provider:{provider}"
