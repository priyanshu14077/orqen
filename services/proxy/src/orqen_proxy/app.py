"""The LLM proxy: the only route from a sandbox to a model.

`POST /v1/messages` accepts the Anthropic Messages format with a run token as the API
key. For each call the proxy:

1. looks up the run token (401 if unknown or expired);
2. refuses models outside the problem's allowlist (400) and spent budgets (402);
3. caps `max_tokens` at what is left of the budget;
4. forwards to the configured provider (500 if the provider fails);
5. adds the tokens to the run's spend and writes an `ops.llm_usage` row with its cost.
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core import runs
from orqen_core.db import DbRole, make_engine, tenant_tx
from orqen_core.logging import configure_logging, get_logger
from orqen_core.models import LlmPurpose
from orqen_core.runs import RunGrant
from orqen_core.settings import get_settings
from orqen_proxy.providers import FakeProvider, Provider, ProviderFailure
from orqen_proxy.wire import MessagesRequest, MessagesUsage, error_body

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging("proxy", level=settings.log_level, json=settings.log_json)
    if settings.provider != "fake":
        raise RuntimeError(f"provider {settings.provider!r} is not built yet; use 'fake'")
    app.state.engine = make_engine(settings.database_url)
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.provider = FakeProvider(app.state.engine)
    log.info("proxy.started", provider=settings.provider)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await app.state.engine.dispose()


def refuse(status: int, kind: str, message: str) -> JSONResponse:
    return JSONResponse(error_body(kind, message), status_code=status)


async def record_usage(
    engine: AsyncEngine, grant: RunGrant, model: str, usage: MessagesUsage, latency_ms: int
) -> float:
    """Write one `ops.llm_usage` row, priced from the latest `billing.model_prices` row
    for the model. A model with no price costs 0 and is logged."""
    async with tenant_tx(engine, grant.tenant_id, DbRole.WORKER) as c:
        found = await c.execute(
            text(
                """
                INSERT INTO ops.llm_usage (tenant_id, submission_id, test_case_id, user_id,
                    purpose, model, input_tokens, output_tokens, latency_ms, cost_usd)
                SELECT :t, :s, :tc, :u, :purpose, :model, :inp, :out, :lat,
                    coalesce((
                        SELECT (:inp * input_usd_per_mtok + :out * output_usd_per_mtok) / 1e6
                        FROM billing.model_prices
                        WHERE model = :model AND effective_from <= now()
                        ORDER BY effective_from DESC LIMIT 1
                    ), 0)
                RETURNING cost_usd
                """
            ),
            {
                "t": grant.tenant_id,
                "s": grant.submission_id,
                "tc": grant.test_case_id,
                "u": grant.user_id,
                "purpose": LlmPurpose.AGENT.value,
                "model": model,
                "inp": usage.input_tokens,
                "out": usage.output_tokens,
                "lat": latency_ms,
            },
        )
        cost = float(found.scalar_one())
    if cost == 0:
        log.warning("proxy.model_unpriced", model=model)
    return cost


def create_app() -> FastAPI:
    app = FastAPI(title="Orqen LLM proxy", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/messages")
    async def messages(
        request: Request, x_api_key: Annotated[str | None, Header()] = None
    ) -> JSONResponse:
        redis: Redis = request.app.state.redis
        grant = await runs.load(redis, x_api_key) if x_api_key else None
        if grant is None:
            return refuse(401, "authentication_error", "unknown or expired run token")
        try:
            req = MessagesRequest.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            return refuse(400, "invalid_request_error", str(exc)[:500])
        if req.model not in grant.models:
            return refuse(400, "invalid_request_error", f"model {req.model!r} is not allowed")
        if grant.remaining_tokens == 0:
            return refuse(402, "budget_exceeded", "the run's token budget is spent")
        req.max_tokens = min(req.max_tokens, grant.remaining_tokens)

        provider: Provider = request.app.state.provider
        started = time.monotonic()
        try:
            resp = await provider.create(req, grant)
        except ProviderFailure as exc:
            log.warning("proxy.provider_failed", error=str(exc))
            return refuse(500, "api_error", str(exc))
        latency_ms = int((time.monotonic() - started) * 1000)

        spent = resp.usage.input_tokens + resp.usage.output_tokens
        await runs.spend(redis, x_api_key or "", spent)
        cost = await record_usage(
            request.app.state.engine, grant, req.model, resp.usage, latency_ms
        )
        log.info(
            "proxy.call",
            submission_id=str(grant.submission_id),
            test_case_id=str(grant.test_case_id),
            model=req.model,
            tokens=spent,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
        return JSONResponse(resp.model_dump())

    return app


app = create_app()
