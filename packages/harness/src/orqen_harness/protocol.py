"""The contract between the executor and the harness.

The executor writes one `Task` as JSON to the harness's stdin and reads one `Result`
as JSON from its stdout. The task carries a run token, never a provider key: the
proxy behind `proxy_url` is the only thing that can reach a model.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orqen_harness.adapter import ToolSpec, Usage


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proxy_url: str
    run_token: str
    model: str
    system: str  # the contestant's prompt
    input: Any  # the test case input, sent to the model as JSON
    max_steps: int = Field(gt=0)
    max_tokens: int = Field(default=1024, gt=0)
    temperature: float = 0.0
    tools: list[ToolSpec] = []


class ResultStatus(StrEnum):
    OK = "ok"  # the model gave a final answer
    MAX_STEPS = "max_steps"  # still calling tools when the step limit ran out
    BUDGET = "budget"  # the proxy refused a call: token budget spent
    REJECTED = "rejected"  # the proxy refused the request itself
    PROVIDER_ERROR = "provider_error"  # infrastructure fault, worth a retry


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResultStatus
    output: Any = None  # the final answer, parsed as JSON when it is JSON
    text: str = ""  # the final answer as the model wrote it
    steps: int = 0
    usage: Usage = Usage()
    error: str | None = None
