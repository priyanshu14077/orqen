import re
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from orqen_core.models import (
    EvalRuleStatus,
    LlmPurpose,
    Mode,
    Role,
    SubmissionKind,
    SubmissionMsg,
    SubmissionStatus,
    SubscriptionStatus,
    Verdict,
)
from orqen_core.models import (
    TestCaseMsg as CaseMsg,  # aliased so pytest doesn't try to collect it
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations/versions"
MIGRATION = "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("0*.py")))


def submission_msg() -> SubmissionMsg:
    return SubmissionMsg(
        tenant_id=uuid4(),
        trace_id="abc123",
        submission_id=uuid4(),
        user_id=uuid4(),
        problem_id=uuid4(),
        mode=Mode.SUBMIT,
    )


def test_stream_payload_round_trips_through_redis_fields() -> None:
    msg = submission_msg()
    fields = msg.to_fields()
    assert set(fields) == {"v", "data"}
    # redis-py returns bytes unless decode_responses is on; both must parse.
    as_bytes = {k.encode(): v.encode() for k, v in fields.items()}
    assert SubmissionMsg.from_fields(fields) == msg
    assert SubmissionMsg.from_fields(as_bytes) == msg


def test_unknown_schema_version_is_rejected() -> None:
    fields = submission_msg().to_fields() | {"v": "99"}
    with pytest.raises(ValueError, match="unsupported schema version"):
        SubmissionMsg.from_fields(fields)


def test_payloads_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CaseMsg.model_validate(
            {
                "tenant_id": uuid4(),
                "trace_id": "t",
                "submission_id": uuid4(),
                "test_case_id": uuid4(),
                "surprise": 1,
            }
        )


def test_only_system_error_is_retryable() -> None:
    assert [v for v in Verdict if v.retryable] == [Verdict.SYSTEM_ERROR]


@pytest.mark.parametrize(
    ("enum", "column"),
    [
        (Role, "role"),
        (SubmissionKind, "kind"),
        (Mode, "mode"),
        (SubmissionStatus, "status"),
        (Verdict, "verdict"),
        (EvalRuleStatus, "status"),
        (LlmPurpose, "purpose"),
        (SubscriptionStatus, "status"),
    ],
)
def test_enum_matches_a_check_constraint_in_the_migration(enum: type[StrEnum], column: str) -> None:
    """The Python enums and the SQL CHECKs are written twice; this keeps them equal."""
    checks = re.findall(rf"CHECK \({column} IN \(([^)]*)\)\)", MIGRATION)
    values = [set(re.findall(r"'([^']+)'", c)) for c in checks]
    assert {e.value for e in enum} in values
