from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from orqen_core.db import make_engine
from orqen_core.logging import TRACE_HEADER, configure_logging, get_logger, new_trace_id
from orqen_core.settings import get_settings
from orqen_gateway import api, live, reads
from orqen_gateway.auth import supabase_verifier

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging("gateway", level=settings.log_level, json=settings.log_json)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.http = httpx.AsyncClient(timeout=10)
    app.state.verifier = (
        supabase_verifier(settings.supabase_url, app.state.http) if settings.supabase_url else None
    )
    log.info("gateway.started", auth=settings.supabase_url is not None)
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.redis.aclose()
        await app.state.engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Orqen gateway", lifespan=lifespan)
    for module in (api, reads, live):
        app.include_router(module.router)

    @app.middleware("http")
    async def trace_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        tid = request.headers.get(TRACE_HEADER) or new_trace_id()
        request.state.trace_id = tid
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
