from typing import Any

import pytest

from orqen_core.models import Verdict
from orqen_workers.grading import UnsupportedRule, grade
from scripts.seed import EVAL_RULE_V1

EXPECTED = {"vendor": "Hooli", "date": "2026-08-19", "total": 64.2, "currency": "AUD"}


def test_a_correct_answer_passes_every_gate() -> None:
    g = grade(EVAL_RULE_V1, dict(EXPECTED), EXPECTED)
    assert g.verdict is Verdict.PASS
    assert g.score == 1.0
    assert all(g.criteria.values())


def test_a_total_within_tolerance_still_passes() -> None:
    assert grade(EVAL_RULE_V1, EXPECTED | {"total": 64.205}, EXPECTED).verdict is Verdict.PASS


@pytest.mark.parametrize(
    ("output", "score"),
    [
        (EXPECTED | {"currency": "USD"}, 0.667),  # fields gate fails
        (EXPECTED | {"total": "64.20"}, 0.667),  # a string is not a number
        ({"vendor": "Hooli"}, 0.0),  # missing keys fail all three
        ("not json", 0.0),
    ],
)
def test_each_failed_gate_costs_its_share(output: Any, score: float) -> None:
    g = grade(EVAL_RULE_V1, output, EXPECTED)
    assert g.verdict is Verdict.FAIL
    assert g.score == score


def test_rules_this_grader_cannot_run_are_refused() -> None:
    with pytest.raises(UnsupportedRule):
        grade({"grading": {"gates": [{"type": "regex"}]}}, {}, {})
    with pytest.raises(UnsupportedRule):
        grade({"grading": {"gates": [], "judge": {"model": "x"}}}, {}, {})
