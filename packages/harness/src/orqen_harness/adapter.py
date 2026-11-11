"""The provider-neutral seam between the agent loop and a model.

The loop only ever talks to a `ModelAdapter`. In the sandbox the adapter is
`MessagesApiAdapter`, which speaks the Anthropic Messages format to the Orqen proxy;
the proxy decides which provider answers. Tests use in-memory adapters.
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


class BudgetExceeded(Exception):
    """The proxy refused the call because the run's token budget is spent."""


class ProviderError(Exception):
    """The model provider or the proxy failed. Infrastructure, so the run is retried."""


class RequestRejected(Exception):
    """The proxy rejected the request itself, such as a model outside the allowlist."""
