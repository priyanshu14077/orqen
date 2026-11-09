from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from orqen_core import streams
from orqen_core.settings import get_settings
from orqen_gateway.app import create_app

from ..conftest import TestSettings

pytestmark = pytest.mark.integration


async def test_ensure_groups_creates_every_group_once(redis: Redis) -> None:
    first = await streams.ensure_groups(redis)
    second = await streams.ensure_groups(redis)
    assert first == list(streams.ALL)
    assert second == []
    for stream in streams.ALL:
        groups = await redis.xinfo_groups(stream.name)
        assert [g["name"].decode() for g in groups] == [stream.group]


async def test_a_group_created_late_still_sees_earlier_messages(redis: Redis) -> None:
    """Groups start at id 0, so nothing added before bootstrap is skipped."""
    await redis.xadd(streams.SUBMISSIONS.name, {"v": "1", "data": "{}"})
    await streams.ensure_groups(redis)
    # RESP2 returns a list; the stub also allows RESP3's dict shape.
    got = cast(
        list[Any],
        await redis.xreadgroup(
            streams.SUBMISSIONS.group, "c1", {streams.SUBMISSIONS.name: ">"}, count=10
        ),
    )
    [(_, entries)] = got
    assert len(entries) == 1


def test_gateway_is_ready_when_postgres_and_redis_answer(
    migrated_db: str, test_settings: TestSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORQEN_DATABASE_URL", migrated_db)
    monkeypatch.setenv("ORQEN_REDIS_URL", test_settings.test_redis_url)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            ready = client.get("/readyz", headers={"X-Trace-ID": "trace-1"})
            assert client.get("/healthz").json() == {"status": "ok"}
    finally:
        get_settings.cache_clear()
    assert ready.status_code == 200
    assert ready.json() == {"postgres": "ok", "redis": "ok"}
    assert ready.headers["X-Trace-ID"] == "trace-1"
