"""Backends the proxy forwards to.

`FakeProvider` stands in for a model so the whole pipeline runs in CI without a key.
It answers each test with the test's expected output, read from Postgres through the
run's grant, so a normal submission scores full marks. Markers in the contestant's
prompt make it misbehave on purpose:

    #fake:wrong      every field of the answer is wrong
    #fake:slow=1.5   sleep 1.5 seconds before answering
    #fake:error      fail as a provider outage would (HTTP 500)
"""

import asyncio
import json
import re
import uuid
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core.db import DbRole, tenant_tx
from orqen_core.runs import RunGrant
from orqen_proxy.wire import MessagesRequest, MessagesResponse, MessagesUsage

SLOW = re.compile(r"#fake:slow=(\d+(?:\.\d+)?)")


class ProviderFailure(Exception):
    """The provider failed. The proxy answers 500 and the run is retried."""


class Provider(Protocol):
    async def create(self, req: MessagesRequest, grant: RunGrant) -> MessagesResponse: ...


def estimate_tokens(s: str) -> int:
    """About four characters per token, the usual rule of thumb for English."""
    return max(1, len(s) // 4)


def wrong(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value + 1000
    return "wrong"


class FakeProvider:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, req: MessagesRequest, grant: RunGrant) -> MessagesResponse:
        system = req.system_text()
        if "#fake:error" in system:
            raise ProviderFailure("fake provider outage (#fake:error)")
        if m := SLOW.search(system):
            await asyncio.sleep(float(m.group(1)))
        answer = await self._expected(grant)
        if "#fake:wrong" in system and isinstance(answer, dict):
            answer = {k: wrong(v) for k, v in answer.items()}
        out = json.dumps(answer, ensure_ascii=False)
        return MessagesResponse(
            id=f"msg_fake_{uuid.uuid4().hex[:24]}",
            model=req.model,
            content=[{"type": "text", "text": out}],
            stop_reason="end_turn",
            usage=MessagesUsage(
                input_tokens=estimate_tokens(req.message_text()),
                output_tokens=estimate_tokens(out),
            ),
        )

    async def _expected(self, grant: RunGrant) -> Any:
        async with tenant_tx(self._engine, grant.tenant_id, DbRole.WORKER) as c:
            found = await c.execute(
                text("SELECT expected FROM authoring.test_cases WHERE id = :id"),
                {"id": grant.test_case_id},
            )
            return found.scalar_one()
