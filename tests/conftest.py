import argparse
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from orqen_core.db import make_engine
from scripts import seed

ROOT = Path(__file__).resolve().parent.parent


class TestSettings(BaseSettings):
    __test__ = False
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="ORQEN_", extra="ignore")

    test_database_url: str = "postgresql+psycopg://orqen:orqen@localhost:5433/orqen_test"
    test_redis_url: str = "redis://localhost:6380/15"


@pytest.fixture(scope="session")
def test_settings() -> TestSettings:
    s = TestSettings()
    url = s.test_database_url
    if "supabase" in url or not url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.exit(f"refusing to run against a non-test database: {url}")
    return s


def alembic_config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    return cfg


# The parts of a Supabase database that the migrations react to: the Data API roles
# and service_role with Supabase's default grants on new public tables, and a minimal auth.users.
# Without them, the Supabase branches of migration 0002 would never run in tests.
SUPABASE_STUB = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
    END IF;
END
$$;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT TRUNCATE, TRIGGER, REFERENCES ON TABLES
    TO service_role;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (id uuid PRIMARY KEY, email text UNIQUE);
"""


def stub_supabase(url: str) -> None:
    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            conn.execute(text(SUPABASE_STUB))
    finally:
        eng.dispose()


@pytest.fixture(scope="session")
def migrated_db(test_settings: TestSettings) -> Iterator[str]:
    """Rebuild the test database from scratch: exercises downgrade and upgrade."""
    cfg = alembic_config(test_settings.test_database_url)
    command.downgrade(cfg, "base")
    stub_supabase(test_settings.test_database_url)
    command.upgrade(cfg, "head")
    yield test_settings.test_database_url


@pytest.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_db)
    yield eng
    await eng.dispose()


class StubAuth:
    """Stands in for Supabase Auth by writing to the stubbed auth.users table."""

    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def ensure_user(self, email: str) -> UUID:
        user_id = seed.sid("user", email)
        await self.conn.execute(
            text("INSERT INTO auth.users (id, email) VALUES (:id, :email) ON CONFLICT DO NOTHING"),
            {"id": user_id, "email": email},
        )
        return user_id


# A second tenant, so tests can check that nothing crosses between tenants.
RIVAL = "rival"
RIVAL_ADMIN = "admin@rival.test"
RIVAL_CONTESTANT = "carol@rival.test"


async def seed_all(conn: AsyncConnection) -> None:
    auth = StubAuth(conn)
    await seed.seed(conn, auth)
    await seed.seed_tenant(conn, auth, RIVAL, "Rival", RIVAL_ADMIN, (RIVAL_CONTESTANT,))


@pytest.fixture(scope="session")
async def seeded(engine: AsyncEngine) -> AsyncEngine:
    async with engine.begin() as conn:
        await seed_all(conn)
    return engine


@pytest.fixture
async def redis(test_settings: TestSettings) -> AsyncIterator[Redis]:
    client = Redis.from_url(test_settings.test_redis_url)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
