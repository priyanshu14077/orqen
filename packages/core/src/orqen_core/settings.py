from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ORQEN_", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    # Supabase Postgres through the Supavisor session pooler (IPv4, port 5432).
    database_url: str
    # Migrations need a single real Postgres session, so Supabase recommends the
    # direct connection. Falls back to database_url when unset.
    migration_database_url: str | None = None
    redis_url: str = "redis://localhost:6380/0"

    # Supabase Auth owns users and passwords. The secret key (sb_secret_...) is for
    # server-side admin calls only and must never reach a browser or a sandbox.
    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None

    # Only the proxy reads this. Nothing that runs in the sandbox may ever see it.
    anthropic_api_key: SecretStr | None = None
    # Which backend the proxy forwards to. `fake` answers every test with its
    # expected output, so the whole pipeline runs without a provider key.
    provider: Literal["fake", "anthropic"] = "fake"
    # Where sandboxes reach the proxy. The executor puts this in each task.
    proxy_url: str = "http://localhost:8080"

    # The tenant that signed-in users join. Orqen runs one global platform.
    platform_tenant: str = "orqen"
    # A stream message pending this long is presumed lost with its worker and is
    # claimed by another one.
    claim_idle_ms: int = 60_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
