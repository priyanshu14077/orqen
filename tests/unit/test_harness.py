import json
from typing import Any

import httpx
import pytest

from orqen_harness.adapter import (
    BudgetExceeded,
    Message,
    ModelParams,
    ProviderError,
    ToolCall,
    ToolSpec,
    Turn,
    Usage,
)
from orqen_harness.loop import parse_output, run
from orqen_harness.messages_api import MessagesApiAdapter, to_wire
from orqen_harness.protocol import ResultStatus, Task


def task(**overrides: Any) -> Task:
    fields: dict[str, Any] = {
        "proxy_url": "http://proxy",
        "run_token": "orq_run_x",
        "model": "claude-haiku-4-5",
        "system": "Extract the fields.",
        "input": {"text": "Invoice"},
        "max_steps": 3,
    }
    return Task(**(fields | overrides))


class Scripted:
    """A ModelAdapter that replays turns, or raises the exceptions it is given."""

    def __init__(self, *turns: Turn | Exception) -> None:
        self.turns = list(turns)
        self.seen: list[list[Message]] = []

    async def complete(
        self, messages: list[Message], tools: list[ToolSpec], params: ModelParams
    ) -> Turn:
        self.seen.append(list(messages))
        nxt = self.turns.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def say(text: str, *calls: ToolCall) -> Turn:
    return Turn(
        text=text,
        tool_calls=list(calls),
        stop_reason="tool_use" if calls else "end_turn",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ("not json", "not json"),
    ],
)
def test_parse_output_reads_json_with_or_without_a_fence(text: str, parsed: Any) -> None:
    assert parse_output(text) == parsed


async def test_a_final_answer_ends_the_loop() -> None:
    model = Scripted(say('{"total": 1}'))
    result = await run(task(), model)
    assert result.status is ResultStatus.OK
    assert result.output == {"total": 1}
    assert result.steps == 1
    assert model.seen[0][0].content == '{"text": "Invoice"}'


async def test_tool_calls_get_an_error_result_and_the_loop_continues() -> None:
    model = Scripted(say("", ToolCall(id="t1", name="lookup", input={})), say("done"))
    result = await run(task(), model)
    assert result.status is ResultStatus.OK
    assert result.steps == 2
    assert result.usage == Usage(input_tokens=20, output_tokens=10)
    tool_reply = model.seen[1][-1]
    assert tool_reply.role == "tool"
    assert tool_reply.tool_call_id == "t1"


async def test_the_step_limit_stops_a_model_that_never_answers() -> None:
    call = ToolCall(id="t", name="x", input={})
    result = await run(task(max_steps=2), Scripted(say("", call), say("", call)))
    assert result.status is ResultStatus.MAX_STEPS
    assert result.steps == 2


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (BudgetExceeded("spent"), ResultStatus.BUDGET),
        (ProviderError("down"), ResultStatus.PROVIDER_ERROR),
    ],
)
async def test_proxy_refusals_end_the_run(error: Exception, status: ResultStatus) -> None:
    result = await run(task(), Scripted(error))
    assert result.status is status
    assert result.error == str(error)


def test_consecutive_tool_results_share_one_user_turn() -> None:
    calls = [ToolCall(id="a", name="x", input={}), ToolCall(id="b", name="x", input={})]
    wire = to_wire(
        [
            Message(role="user", content="hi"),
            Message(role="assistant", tool_calls=calls),
            Message(role="tool", tool_call_id="a", content="r1"),
            Message(role="tool", tool_call_id="b", content="r2"),
        ]
    )
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in wire[2]["content"]] == ["a", "b"]


def proxy(status: int, body: dict[str, Any], seen: list[httpx.Request]) -> httpx.AsyncClient:
    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(reply))


async def test_the_adapter_sends_the_run_token_and_reads_the_reply() -> None:
    seen: list[httpx.Request] = []
    body = {
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 7, "output_tokens": 2},
    }
    async with proxy(200, body, seen) as client:
        adapter = MessagesApiAdapter("http://proxy/", "orq_run_x", client)
        turn = await adapter.complete(
            [Message(role="user", content="hi")], [], ModelParams(model="m", system="be brief")
        )
    assert turn.text == "ok"
    assert turn.usage.input_tokens == 7
    assert str(seen[0].url) == "http://proxy/v1/messages"
    assert seen[0].headers["x-api-key"] == "orq_run_x"
    assert json.loads(seen[0].content)["system"] == "be brief"


@pytest.mark.parametrize(("status", "error"), [(402, BudgetExceeded), (500, ProviderError)])
async def test_the_adapter_maps_proxy_errors(status: int, error: type[Exception]) -> None:
    body = {"type": "error", "error": {"type": "x", "message": "no"}}
    async with proxy(status, body, []) as client:
        adapter = MessagesApiAdapter("http://proxy", "t", client)
        with pytest.raises(error, match="no"):
            await adapter.complete([Message(role="user", content="hi")], [], ModelParams(model="m"))
