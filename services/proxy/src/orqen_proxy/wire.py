"""The subset of the Anthropic Messages API that the proxy accepts and returns."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MessagesRequest(BaseModel):
    # Unknown fields pass through to the provider untouched.
    model_config = ConfigDict(extra="allow")

    model: str
    max_tokens: int = Field(gt=0)
    messages: list[dict[str, Any]]
    system: str | list[dict[str, Any]] | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] | None = None

    def system_text(self) -> str:
        if isinstance(self.system, list):
            return "".join(b.get("text", "") for b in self.system)
        return self.system or ""

    def message_text(self) -> str:
        """Every text the request carries, for estimating input tokens."""
        parts = [self.system_text()]
        for m in self.messages:
            content = m.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts += [str(b.get("text") or b.get("content") or "") for b in content]
        return "".join(parts)


class MessagesUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class MessagesResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    model: str
    content: list[dict[str, Any]]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence"]
    stop_sequence: str | None = None
    usage: MessagesUsage


def error_body(kind: str, message: str) -> dict[str, Any]:
    """The Messages API error shape, so any Anthropic client can read our refusals."""
    return {"type": "error", "error": {"type": kind, "message": message}}
