"""The read loop every worker shares: XREADGROUP, handle, XACK, and reclaim lost work.

Delivery is at least once. A message is acked only after its handler returns, so a
worker that dies mid-job leaves the message pending. Every consumer reclaims messages
that have been pending longer than `claim_idle_ms` with XAUTOCLAIM, so another worker
finishes the job. A message delivered more than `max_deliveries` times, or one that
can't be parsed, goes to the dead-letter stream instead.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from pydantic import ValidationError
from redis.asyncio import Redis

from orqen_core import streams
from orqen_core.logging import get_logger
from orqen_core.models import DlqMsg
from orqen_core.streams import Stream

log = get_logger(__name__)

Fields = dict[Any, Any]
Handler = Callable[[str, Fields], Awaitable[None]]


class Poison(Exception):
    """The message can never succeed, such as one naming a row that doesn't exist."""


def decode(fields: Fields) -> dict[str, str]:
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }


def queue_wait_ms(msg_id: str) -> int:
    """How long the message waited: stream ids start with their creation time in ms."""
    return max(int(time.time() * 1000) - int(msg_id.split("-")[0]), 0)


@dataclass
class Consumer:
    redis: Redis
    streams: Sequence[Stream]  # same group; earlier streams are read first
    name: str
    handle: Handler
    batch: int = 1
    block_ms: int = 1000
    claim_idle_ms: int = 60_000
    max_deliveries: int = 5
    _last_claim: float = field(default=0.0, init=False)

    @property
    def group(self) -> str:
        return self.streams[0].group

    async def run(self, stop: asyncio.Event) -> None:
        log.info("consumer.started", streams=[s.name for s in self.streams], name=self.name)
        while not stop.is_set():
            await self.step()

    async def step(self) -> int:
        """Reclaim if due, then read and handle one batch. Returns messages handled."""
        jobs: list[tuple[Stream, str, Fields]] = []
        if time.monotonic() - self._last_claim >= self.claim_idle_ms / 2000:
            self._last_claim = time.monotonic()
            for stream in self.streams:
                jobs += [(stream, i, f) for i, f in await self._reclaim(stream)]
        if not jobs:
            got = cast(
                list[Any],
                await self.redis.xreadgroup(
                    self.group,
                    self.name,
                    {s.name: ">" for s in self.streams},
                    count=self.batch,
                    block=self.block_ms,
                ),
            )
            by_name = {s.name: s for s in self.streams}
            for raw_name, entries in got or []:
                name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
                jobs += [(by_name[name], self._id(i), f) for i, f in entries]
        await asyncio.gather(*(self._process(s, i, f) for s, i, f in jobs))
        return len(jobs)

    @staticmethod
    def _id(raw: Any) -> str:
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    async def _reclaim(self, stream: Stream) -> list[tuple[str, Fields]]:
        res: list[Any] = await self.redis.xautoclaim(
            stream.name,
            self.group,
            self.name,
            min_idle_time=self.claim_idle_ms,
            start_id="0-0",
            count=self.batch,
        )
        claimed: list[tuple[str, Fields]] = []
        for raw_id, fields in res[1]:
            msg_id = self._id(raw_id)
            pending = cast(
                list[dict[str, Any]],
                await self.redis.xpending_range(stream.name, self.group, msg_id, msg_id, 1),
            )
            deliveries = int(pending[0]["times_delivered"]) if pending else 1
            log.warning("consumer.reclaimed", stream=stream.name, id=msg_id, deliveries=deliveries)
            if deliveries > self.max_deliveries:
                await self._dead_letter(stream, msg_id, fields, "too many deliveries", deliveries)
            else:
                claimed.append((msg_id, fields))
        return claimed

    async def _process(self, stream: Stream, msg_id: str, fields: Fields) -> None:
        try:
            await self.handle(msg_id, fields)
        except (Poison, ValidationError, ValueError) as exc:
            log.error("consumer.poison", stream=stream.name, id=msg_id, error=str(exc))
            await self._dead_letter(stream, msg_id, fields, f"{type(exc).__name__}: {exc}", 1)
        except Exception:
            # Left pending: XAUTOCLAIM hands it to a worker again after claim_idle_ms.
            log.exception("consumer.failed", stream=stream.name, id=msg_id)
        else:
            await self.redis.xack(stream.name, self.group, msg_id)

    async def _dead_letter(
        self, stream: Stream, msg_id: str, fields: Fields, error: str, deliveries: int
    ) -> None:
        original = decode(fields)
        try:
            data = json.loads(original.get("data", "{}"))
            tenant_id, trace_id = UUID(data["tenant_id"]), str(data.get("trace_id", ""))
        except (ValueError, KeyError, TypeError):
            tenant_id, trace_id = UUID(int=0), ""
        msg = DlqMsg(
            tenant_id=tenant_id,
            trace_id=trace_id,
            source_stream=stream.name,
            original=original,
            error=error[:1000],
            deliveries=deliveries,
        )
        await self.redis.xadd(streams.DLQ.name, msg.to_fields())  # type: ignore[arg-type]
        await self.redis.xack(stream.name, self.group, msg_id)
