from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

# Created by migration 0001. Not the table owner, so row-level security applies to it
# once M7 turns RLS on. Request and job transactions run as this role.
APP_ROLE = "orqen_app"


def make_engine(url: str, *, pool_size: int = 5) -> AsyncEngine:
    return create_async_engine(url, pool_size=pool_size, pool_pre_ping=True)


@asynccontextmanager
async def tenant_tx(engine: AsyncEngine, tenant_id: UUID) -> AsyncIterator[AsyncConnection]:
    """A transaction scoped to one tenant.

    `SET LOCAL` ends with the transaction, so a pooled connection never carries one
    tenant's scope into the next request.
    """
    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )
        yield conn
