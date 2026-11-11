"""Run tokens: the only credential a sandbox holds.

The executor mints a token for one test run and passes it to the harness. The proxy
looks the token up to learn whose run it is, which models it may call and how many
tokens it may spend. The token expires shortly after the problem's time limit and is
revoked as soon as the run ends.
"""

import secrets
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

from orqen_core import keys


@dataclass(frozen=True)
class RunGrant:
    tenant_id: UUID
    user_id: UUID
    submission_id: UUID
    test_case_id: UUID
    models: tuple[str, ...]
    budget_tokens: int
    used_tokens: int = 0

    @property
    def remaining_tokens(self) -> int:
        return max(self.budget_tokens - self.used_tokens, 0)


def _s(v: bytes | str) -> str:
    return v.decode() if isinstance(v, bytes) else v


async def mint(redis: Redis, grant: RunGrant, ttl_s: int) -> str:
    token = "orq_run_" + secrets.token_urlsafe(24)
    key = keys.run_token(token)
    await redis.hset(
        key,
        mapping={
            "tenant_id": str(grant.tenant_id),
            "user_id": str(grant.user_id),
            "submission_id": str(grant.submission_id),
            "test_case_id": str(grant.test_case_id),
            "models": ",".join(grant.models),
            "budget_tokens": grant.budget_tokens,
            "used_tokens": grant.used_tokens,
        },
    )
    await redis.expire(key, ttl_s)
    return token


async def load(redis: Redis, token: str) -> RunGrant | None:
    raw = await redis.hgetall(keys.run_token(token))
    if not raw:
        return None
    f = {_s(k): _s(v) for k, v in raw.items()}
    return RunGrant(
        tenant_id=UUID(f["tenant_id"]),
        user_id=UUID(f["user_id"]),
        submission_id=UUID(f["submission_id"]),
        test_case_id=UUID(f["test_case_id"]),
        models=tuple(f["models"].split(",")),
        budget_tokens=int(f["budget_tokens"]),
        used_tokens=int(f["used_tokens"]),
    )


async def spend(redis: Redis, token: str, tokens: int) -> int | None:
    """Add `tokens` to the run's spend and return the new total, or None when the token
    is gone. Checking first keeps HINCRBY from recreating a revoked token without a TTL."""
    key = keys.run_token(token)
    if not await redis.exists(key):
        return None
    return int(await redis.hincrby(key, "used_tokens", tokens))


async def revoke(redis: Redis, token: str) -> None:
    await redis.delete(keys.run_token(token))
