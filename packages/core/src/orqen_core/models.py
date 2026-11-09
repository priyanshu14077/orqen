"""Domain enums and the payloads that travel on Redis Streams.

The enum values match the CHECK constraints in migration 0001; change both together.
"""

from enum import StrEnum
from typing import Any, ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class SubmissionKind(StrEnum):
    PROMPT = "prompt"
    CODE = "code"


class Mode(StrEnum):
    RUN = "run"  # sample tests only, fast lane
    SUBMIT = "submit"  # hidden tests, counts for the leaderboard


class SubmissionStatus(StrEnum):
    WAITING = "WAITING"  # held back by the tenant's in-flight cap
    QUEUED = "QUEUED"
    EXPANDING = "EXPANDING"
    RUNNING = "RUNNING"
    AGGREGATING = "AGGREGATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TLE = "TLE"
    MLE = "MLE"
    BUDGET = "BUDGET"
    SYSTEM_ERROR = "SYSTEM_ERROR"

    @property
    def retryable(self) -> bool:
        """User faults are final; only infrastructure faults are retried."""
        return self is Verdict.SYSTEM_ERROR


class EvalRuleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class LlmPurpose(StrEnum):
    AGENT = "agent"
    JUDGE = "judge"


class StreamMessage(BaseModel):
    """A stream entry is one field, `data`, holding this model as JSON, plus `v`.

    `v` lets a worker refuse a payload shape it doesn't understand instead of
    misreading it during a rolling deploy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: ClassVar[str] = "1"

    tenant_id: UUID
    trace_id: str

    def to_fields(self) -> dict[str, str]:
        return {"v": self.schema_version, "data": self.model_dump_json()}

    @classmethod
    def from_fields(cls, fields: dict[Any, Any]) -> Self:
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        if decoded.get("v") != cls.schema_version:
            raise ValueError(f"{cls.__name__}: unsupported schema version {decoded.get('v')!r}")
        return cls.model_validate_json(decoded["data"])


class SubmissionMsg(StreamMessage):
    submission_id: UUID
    user_id: UUID
    problem_id: UUID
    mode: Mode


class TestCaseMsg(StreamMessage):
    submission_id: UUID
    test_case_id: UUID
    attempt: int = 1


class GradingMsg(StreamMessage):
    submission_id: UUID
    test_case_id: UUID
    attempt: int
    output: Any = None
    exec_verdict: Verdict | None = None  # set when execution already decided (TLE, MLE...)
    latency_ms: int
    queue_wait_ms: int = 0


class DlqMsg(StreamMessage):
    source_stream: str
    original: dict[str, str]
    error: str
    deliveries: int
