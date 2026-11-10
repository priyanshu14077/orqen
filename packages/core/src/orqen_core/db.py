from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from orqen_core.models import Role


class DbRole(StrEnum):
    """The database roles created by migration 0004.

    None of them owns a table, so row-level security applies to all of them. The human
    roles nest: orqen_admin contains orqen_setter, which contains orqen_contestant.
    """

    CONTESTANT = "orqen_contestant"
    SETTER = "orqen_setter"
    ADMIN = "orqen_admin"
    WORKER = "orqen_worker"  # orchestrator, executors, grader, proxy, webhooks

    @classmethod
    def for_member(cls, role: Role) -> "DbRole":
        return {
            Role.CONTESTANT: cls.CONTESTANT,
            Role.SETTER: cls.SETTER,
            Role.ADMIN: cls.ADMIN,
        }[role]


def make_engine(url: str, *, pool_size: int = 5) -> AsyncEngine:
    return create_async_engine(url, pool_size=pool_size, pool_pre_ping=True)


@asynccontextmanager
async def tenant_tx(
    engine: AsyncEngine,
    tenant_id: UUID,
    role: DbRole,
    user_id: UUID | None = None,
) -> AsyncGenerator[AsyncConnection, None]:
    """A transaction that runs as `role`, scoped to one tenant and, for people, one user.

    Row-level security policies read `app.tenant_id` and `app.user_id`. `SET LOCAL`
    ends with the transaction, so a pooled connection never carries one request's
    scope into the next.
    """
    if role is not DbRole.WORKER and user_id is None:
        raise ValueError(f"{role} acts for a person and needs a user_id")
    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {role.value}"))
        await conn.execute(
            text(
                "SELECT set_config('app.tenant_id', :tid, true),"
                " set_config('app.user_id', :uid, true)"
            ),
            {"tid": str(tenant_id), "uid": str(user_id) if user_id else ""},
        )
        yield conn
