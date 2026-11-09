import argparse
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core.db import make_engine

ROOT = Path(__file__).resolve().parent.parent


class TestSettings(BaseSettings):
    __test__ = False
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="ORQEN_", extra="ignore")

    test_database_url: str = "postgresql+psycopg://orqen:orqen@localhost:5433/orqen_test"
    test_redis_url: str = "redis://localhost:6380/15"


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    s = TestSettings()
    if not s.test_database_url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.exit(f"refusing to run against a non-test database: {s.test_database_url}")
    return s


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return cfg


@pytest.fixture(scope="session")
def migrated_db(test_settings: TestSettings) -> Iterator[str]:
    """Rebuild the test database from scratch: exercises downgrade and upgrade."""
    cfg = alembic_config(test_settings.test_database_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield test_settings.test_database_url


@pytest.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest.fixture
async def redis(test_settings: TestSettings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.test_redis_url)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
