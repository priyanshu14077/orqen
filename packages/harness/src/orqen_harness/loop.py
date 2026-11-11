"""The agent loop: call the model, run the tools it asks for, repeat until it answers.

M1 problems have no tools, so a tool call gets an error result and the loop goes on.
"""

import json
import re
from typing import Any

from orqen_harness.adapter import (
    BudgetExceeded,
    Message,
    ModelAdapter,
    ModelParams,
    ProviderError,
    RequestRejected,
    Usage,
)
from orqen_harness.protocol import Result, ResultStatus, Task

FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_output(text: str) -> Any:
    """The answer as JSON when it is JSON, with or without a code fence; else the text."""
    stripped = text.strip()
    if m := FENCE.match(stripped):
        stripped = m.group(1)
    try:
        return json.loads(stripped)
    except ValueError:
        return text


async def run(task: Task, adapter: ModelAdapter) -> Result:
    messages = [Message(role="user", content=json.dumps(task.input, ensure_ascii=False))]
    params = ModelParams(
        model=task.model,
        temperature=task.temperature,
        max_tokens=task.max_tokens,
        system=task.system,
    )
    usage = Usage()
    tool_names = {t.name for t in task.tools}

    def stop(status: ResultStatus, steps: int, error: str) -> Result:
        return Result(status=status, steps=steps, usage=usage, error=error)

    for step in range(1, task.max_steps + 1):
        try:
            turn = await adapter.complete(messages, task.tools, params)
        except BudgetExceeded as exc:
            return stop(ResultStatus.BUDGET, step - 1, str(exc))
        except RequestRejected as exc:
            return stop(ResultStatus.REJECTED, step - 1, str(exc))
        except ProviderError as exc:
            return stop(ResultStatus.PROVIDER_ERROR, step - 1, str(exc))
        usage = Usage(
            input_tokens=usage.input_tokens + turn.usage.input_tokens,
            output_tokens=usage.output_tokens + turn.usage.output_tokens,
        )
        messages.append(Message(role="assistant", content=turn.text, tool_calls=turn.tool_calls))
        if not turn.tool_calls:
            return Result(
                status=ResultStatus.OK,
                output=parse_output(turn.text),
                text=turn.text,
                steps=step,
                usage=usage,
            )
        for call in turn.tool_calls:
            reason = "is not implemented yet" if call.name in tool_names else "does not exist"
            messages.append(
                Message(role="tool", tool_call_id=call.id, content=f"error: {call.name} {reason}")
            )
    return stop(ResultStatus.MAX_STEPS, task.max_steps, "no final answer within max_steps")
