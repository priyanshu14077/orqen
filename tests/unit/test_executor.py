from orqen_core.models import Verdict
from orqen_harness.protocol import ResultStatus, Task
from orqen_workers.executor import pick_model, run_harness, sandbox_env

TASK = Task(
    proxy_url="http://127.0.0.1:9",  # nothing listens on the discard port
    run_token="orq_run_x",
    model="claude-haiku-4-5",
    system="x",
    input={"text": "x"},
    max_steps=1,
)


async def test_an_unreachable_proxy_is_an_infrastructure_fault() -> None:
    outcome = await run_harness(TASK, timeout_s=30)
    assert outcome.verdict is Verdict.SYSTEM_ERROR
    assert outcome.infrastructure_fault
    assert outcome.result is not None
    assert outcome.result.status is ResultStatus.PROVIDER_ERROR


async def test_a_run_past_the_time_limit_is_tle() -> None:
    outcome = await run_harness(TASK, timeout_s=0.01)
    assert outcome.verdict is Verdict.TLE
    assert not outcome.infrastructure_fault


def test_the_harness_gets_no_secrets_from_the_executor_env() -> None:
    assert set(sandbox_env()) == {"PATH", "PYTHONUNBUFFERED"}


def test_a_model_outside_the_allowlist_falls_back_to_the_first() -> None:
    assert pick_model({"model": "gpt-5"}, ["claude-haiku-4-5"]) == "claude-haiku-4-5"
    assert pick_model({"model": "b"}, ["a", "b"]) == "b"
