"""Request dependencies shared by every v1 route: who the caller is and how they act.

principal       the verified Supabase user from `Authorization: Bearer`
platform_tenant the tenant every user joins
member          principal + tenant + membership role; `member.tx(engine)` opens a
                transaction as that role, so row-level security applies
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core.db import DbRole, tenant_tx
from orqen_core.models import Role
from orqen_gateway.auth import AuthError, JwtVerifier, Principal

# SQLSTATEs raised by the database, and what the caller sees.
REFUSALS = {
    "OQ402": 402,  # no live subscription, or the plan's submission cap
    "OQ429": 429,  # runs_per_hour, or a contest's submits per problem
    "42501": 404,  # row-level security: the problem isn't open to this caller
    "23503": 404,  # the problem or contest doesn't exist
}


async def principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "missing bearer token", {"WWW-Authenticate": "Bearer"})
    verifier: JwtVerifier | None = request.app.state.verifier
    if verifier is None:
        raise HTTPException(503, "auth is not configured: set ORQEN_SUPABASE_URL")
    try:
        return await verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(401, str(exc), {"WWW-Authenticate": "Bearer"}) from exc


async def platform_tenant(request: Request) -> UUID:
    """The tenant every user joins. Read once with the login role, before any tenant
    scope exists, then cached."""
    cached: UUID | None = getattr(request.app.state, "tenant_id", None)
    if cached:
        return cached
    engine: AsyncEngine = request.app.state.engine
    slug = request.app.state.settings.platform_tenant
    async with engine.connect() as c:
        found = await c.execute(
            text("SELECT id FROM identity.tenants WHERE slug = :s"), {"s": slug}
        )
        tenant_id = found.scalar_one_or_none()
    if tenant_id is None:
        raise HTTPException(503, f"tenant {slug!r} does not exist; run the seed")
    request.app.state.tenant_id = tenant_id
    return UUID(str(tenant_id))


Caller = Annotated[Principal, Depends(principal)]
Tenant = Annotated[UUID, Depends(platform_tenant)]


async def member_role(engine: AsyncEngine, tenant_id: UUID, user_id: UUID) -> Role:
    async with tenant_tx(engine, tenant_id, DbRole.WORKER) as c:
        found = await c.execute(
            text("SELECT role FROM identity.memberships WHERE tenant_id = :t AND user_id = :u"),
            {"t": tenant_id, "u": user_id},
        )
        role = found.scalar_one_or_none()
    if role is None:
        raise HTTPException(403, "no Orqen account yet: call POST /v1/me first")
    return Role(role)


def refusal(exc: DBAPIError) -> HTTPException | None:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    status = REFUSALS.get(sqlstate or "")
    if status is None:
        return None
    if status == 404:
        return HTTPException(404, "problem not found or not open for submissions")
    diag = getattr(exc.orig, "diag", None)
    return HTTPException(status, getattr(diag, "message_primary", None) or "refused")


@dataclass(frozen=True)
class Member:
    tenant_id: UUID
    user_id: UUID
    role: Role

    @asynccontextmanager
    async def tx(self, engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
        async with tenant_tx(
            engine, self.tenant_id, DbRole.for_member(self.role), self.user_id
        ) as c:
            yield c


async def member(request: Request, caller: Caller, tenant_id: Tenant) -> Member:
    role = await member_role(request.app.state.engine, tenant_id, caller.user_id)
    return Member(tenant_id=tenant_id, user_id=caller.user_id, role=role)


AsMember = Annotated[Member, Depends(member)]
