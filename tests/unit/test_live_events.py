from orqen_gateway.live import ALLOWED, public_event


def test_only_allow_listed_fields_reach_the_browser() -> None:
    leaked = {
        "seq": 4,
        "ts": "t",
        "type": "test",
        "submission_id": "s",
        "test": 5,
        "verdict": "FAIL",
        "output": {"vendor": "secret"},
        "expected": {"vendor": "answer"},
        "trace": ["call"],
    }
    event = public_event(leaked)
    assert event is not None
    assert not {"output", "expected", "trace"} & set(event)
    assert set(event) <= ALLOWED["test"]


def test_unknown_event_types_are_dropped() -> None:
    assert public_event({"type": "debug", "seq": 1, "payload": "x"}) is None
