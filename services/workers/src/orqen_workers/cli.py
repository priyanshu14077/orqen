"""Entry point for every worker: `orqen-workers <command>`.

M0 has only `bootstrap`. The orchestrator, executor, grader and watchdog become
subcommands of the same binary, so compose can scale each one independently.
"""

import argparse
import asyncio

from redis.asyncio import Redis

from orqen_core import streams
from orqen_core.logging import configure_logging, get_logger
from orqen_core.settings import get_settings

log = get_logger(__name__)


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="orqen-workers")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap", help="create Redis streams and consumer groups")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(f"workers.{args.command}", level=settings.log_level, json=settings.log_json)
    if args.command == "bootstrap":
        asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
