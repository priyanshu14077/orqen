from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ORQEN_", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+psycopg://orqen:orqen@localhost:5433/orqen"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: SecretStr = SecretStr("dev-only-change-me")

    # Only the proxy reads this. Nothing that runs in the sandbox may ever see it.
    anthropic_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
