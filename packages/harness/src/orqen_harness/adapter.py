"""The provider-neutral seam between the agent loop and a model.

The loop only ever talks to a `ModelAdapter`. Claude is the first implementation
(M1); adding another provider means adding an adapter, not touching the loop, the
judge or the proxy's callers.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


class Message(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = []
    tool_call_id: str | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class Turn(BaseModel):
    """One model response: either text, tool calls, or both."""

    text: str
    tool_calls: list[ToolCall]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "other"]
    usage: Usage


class ModelParams(BaseModel):
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    system: str | None = None


class ModelAdapter(Protocol):
    async def complete(
        self, messages: list[Message], tools: list[ToolSpec], params: ModelParams
    ) -> Turn: ...
