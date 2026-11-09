from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from orqen_core.db import make_engine
from orqen_core.logging import TRACE_HEADER, configure_logging, get_logger, new_trace_id
from orqen_core.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("gateway", level=settings.log_level, json=settings.log_json)
    app.state.engine = make_engine(settings.database_url)
    app.state.redis = Redis.from_url(settings.redis_url)
    log.info("gateway.started")
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Orqen gateway", lifespan=lifespan)

    @app.middleware("http")
    async def trace_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        tid = request.headers.get(TRACE_HEADER) or new_trace_id()
        with structlog.contextvars.bound_contextvars(trace_id=tid):
            response = await call_next(request)
        response.headers[TRACE_HEADER] = tid
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness: the process is up. Never touches dependencies."""
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        """Readiness: Postgres and Redis both answer."""
        checks: dict[str, str] = {}
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {type(exc).__name__}"
        try:
            await request.app.state.redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {type(exc).__name__}"
        ready = all(v == "ok" for v in checks.values())
        return JSONResponse(checks, status_code=200 if ready else 503)

    return app


app = create_app()
