from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from orqen_core.logging import configure_logging, get_logger
from orqen_core.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("proxy", level=settings.log_level, json=settings.log_json)
    log.info("proxy.started", provider_key_set=settings.anthropic_api_key is not None)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Orqen LLM proxy", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
