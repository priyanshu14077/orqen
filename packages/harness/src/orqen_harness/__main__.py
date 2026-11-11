"""`python -m orqen_harness`: read a `Task` from stdin, write a `Result` to stdout.

Exit code 0 means stdout holds a `Result`. Any other exit code is a harness crash,
which the executor treats as an infrastructure fault.
"""

import asyncio
import sys

import httpx

from orqen_harness.loop import run
from orqen_harness.messages_api import MessagesApiAdapter
from orqen_harness.protocol import Result, Task

HTTP_TIMEOUT_S = 120


async def _main(task: Task) -> Result:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
        return await run(task, MessagesApiAdapter(task.proxy_url, task.run_token, client))


def main() -> int:
    task = Task.model_validate_json(sys.stdin.buffer.read())
    result = asyncio.run(_main(task))
    sys.stdout.write(result.model_dump_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
