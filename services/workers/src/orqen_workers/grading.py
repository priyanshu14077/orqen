"""Deterministic grading: run an eval rule's gates against one output.

A test's score is the share of gates that pass, and the test passes when that share
reaches the rule's `pass_threshold`. LLM judging (`judge`) arrives in M6.

Gate types:

    json_schema        {"schema": {"type": "object", "required": [...]}}
                       (only `type: object` and `required` are checked for now)
    json_fields        {"fields": [...]}  each field equals the expected value
    numeric_tolerance  {"field": ..., "abs_tol": ...}
"""

from dataclasses import dataclass
from typing import Any

from orqen_core.models import Verdict


class UnsupportedRule(Exception):
    """The rule uses something this grader can't evaluate yet."""


@dataclass(frozen=True)
class Grade:
    verdict: Verdict
    score: float
    criteria: dict[str, bool]


def _number(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def check(gate: dict[str, Any], output: Any, expected: Any) -> bool:
    kind = gate.get("type")
    if kind == "json_schema":
        schema = gate.get("schema", {})
        if schema.get("type", "object") != "object":
            raise UnsupportedRule(f"json_schema type {schema.get('type')!r}")
        return isinstance(output, dict) and all(k in output for k in schema.get("required", []))
    if kind == "json_fields":
        if not isinstance(output, dict) or not isinstance(expected, dict):
            return False
        return all(f in output and output[f] == expected.get(f) for f in gate["fields"])
    if kind == "numeric_tolerance":
        if not isinstance(output, dict) or not isinstance(expected, dict):
            return False
        got, want = _number(output.get(gate["field"])), _number(expected.get(gate["field"]))
        return got is not None and want is not None and abs(got - want) <= gate["abs_tol"]
    raise UnsupportedRule(f"gate type {kind!r}")


def grade(spec: dict[str, Any], output: Any, expected: Any) -> Grade:
    rules = spec["grading"]
    if rules.get("judge"):
        raise UnsupportedRule("LLM judge")
    gates = rules.get("gates") or []
    if not gates:
        raise UnsupportedRule("a rule with no gates")
    criteria = {f"{i}:{g['type']}": check(g, output, expected) for i, g in enumerate(gates)}
    score = round(sum(criteria.values()) / len(criteria), 3)
    verdict = Verdict.PASS if score >= rules.get("pass_threshold", 1.0) else Verdict.FAIL
    return Grade(verdict=verdict, score=score, criteria=criteria)
