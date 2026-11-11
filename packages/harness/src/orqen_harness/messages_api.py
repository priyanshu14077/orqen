"""`MessagesApiAdapter`: a `ModelAdapter` that speaks the Anthropic Messages format.

It talks to the Orqen proxy, which authenticates the run token, enforces the budget
and forwards to whichever provider is configured (the fake provider or Claude).
"""

from typing import Any, Literal

import httpx

from orqen_harness.adapter import (
    BudgetExceeded,
    Message,
    ModelParams,
    ProviderError,
    RequestRejected,
    ToolCall,
    ToolSpec,
    Turn,
    Usage,
)

ANTHROPIC_VERSION = "2023-06-01"
StopReason = Literal["end_turn", "tool_use", "max_tokens", "other"]


def to_wire(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert loop messages to Messages API turns.

    Tool results become `tool_result` blocks in a user turn, and consecutive results
    share one turn, because the API requires user and assistant turns to alternate.
    """
    wire: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "user":
            wire.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
                for c in m.tool_calls
            ]
            wire.append({"role": "assistant", "content": blocks})
        else:
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            last = wire[-1] if wire else None
            if last and last["role"] == "user" and isinstance(last["content"], list):
                last["content"].append(block)
            else:
                wire.append({"role": "user", "content": [block]})
    return wire


def from_wire(body: dict[str, Any]) -> Turn:
    text = "".join(b["text"] for b in body["content"] if b["type"] == "text")
    calls = [
        ToolCall(id=b["id"], name=b["name"], input=b["input"])
        for b in body["content"]
        if b["type"] == "tool_use"
    ]
    reason = body.get("stop_reason")
    stop: StopReason = reason if reason in ("end_turn", "tool_use", "max_tokens") else "other"
    usage = body.get("usage", {})
    return Turn(
        text=text,
        tool_calls=calls,
        stop_reason=stop,
        usage=Usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        ),
    )


class MessagesApiAdapter:
    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/messages"
        self._headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        self._client = client

    async def complete(
        self, messages: list[Message], tools: list[ToolSpec], params: ModelParams
    ) -> Turn:
        body: dict[str, Any] = {
            "model": params.model,
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "messages": to_wire(messages),
        }
        if params.system:
            body["system"] = params.system
        if tools:
            body["tools"] = [t.model_dump() for t in tools]
        try:
            resp = await self._client.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"proxy unreachable: {type(exc).__name__}") from exc
        if resp.status_code == 200:
            return from_wire(resp.json())
        message = _error_message(resp)
        if resp.status_code == 402:
            raise BudgetExceeded(message)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise ProviderError(f"{resp.status_code}: {message}")
        raise RequestRejected(f"{resp.status_code}: {message}")


def _error_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return resp.text[:200]
