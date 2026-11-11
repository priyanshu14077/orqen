"""Entry point for every worker: `orqen-workers <command>`.

    bootstrap      create the Redis streams and consumer groups
    orchestrator   expand submissions into test jobs
    executor       run the harness for each test job
    grader         score results and complete submissions
    all            the three workers in one process, for local development

Each worker is its own command so compose can scale them independently. SIGTERM and
SIGINT stop a worker after its current batch.
"""

import argparse
import asyncio
import os
import signal
import socket

from redis.asyncio import Redis

from orqen_core import streams
from orqen_core.db import make_engine
from orqen_core.logging import configure_logging, get_logger
from orqen_core.settings import Settings, get_settings
from orqen_workers.consumer import Consumer
from orqen_workers.executor import Executor
from orqen_workers.grader import Grader
from orqen_workers.orchestrator import Orchestrator

log = get_logger(__name__)
WORKERS = ("orchestrator", "executor", "grader")


async def bootstrap() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    try:
        created = await streams.ensure_groups(redis)
    finally:
        await redis.aclose()
    log.info(
        "streams.bootstrapped",
        created=[f"{s.name}/{s.group}" for s in created],
        total=len(streams.ALL),
    )


async def serve(names: list[str], settings: Settings, concurrency: int) -> None:
    engine = make_engine(settings.database_url, pool_size=max(2, concurrency))
    redis = Redis.from_url(settings.redis_url)
    await streams.ensure_groups(redis)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    me = f"{socket.gethostname()}-{os.getpid()}"

    consumers = []
    for name in names:
        if name == "orchestrator":
            handle = Orchestrator(engine, redis).handle
            lanes = [streams.SUBMISSIONS_PRIORITY, streams.SUBMISSIONS]
            batch = 1
        elif name == "executor":
            handle = Executor(engine, redis, settings.proxy_url).handle
            lanes, batch = [streams.TESTCASES], concurrency
        else:
            handle = Grader(engine, redis).handle
            lanes, batch = [streams.GRADING], concurrency
        consumers.append(
            Consumer(
                redis,
                lanes,
                f"{name}-{me}",
                handle,
                batch=batch,
                claim_idle_ms=settings.claim_idle_ms,
            )
        )
    try:
        await asyncio.gather(*(c.run(stop) for c in consumers))
    finally:
        await redis.aclose()
        await engine.dispose()
        log.info("workers.stopped", workers=names)


def main() -> None:
    parser = argparse.ArgumentParser(prog="orqen-workers")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="create Redis streams and consumer groups")
    for name in (*WORKERS, "all"):
        p = sub.add_parser(name, help=f"run the {name} worker" if name != "all" else "run all")
        p.add_argument("--concurrency", type=int, default=4, help="messages handled at once")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(f"workers.{args.command}", level=settings.log_level, json=settings.log_json)
    if args.command == "bootstrap":
        asyncio.run(bootstrap())
    else:
        names = list(WORKERS) if args.command == "all" else [args.command]
        asyncio.run(serve(names, settings, args.concurrency))


if __name__ == "__main__":
    main()
