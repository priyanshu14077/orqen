"""The whole pipeline, end to end, as separate processes talking over the network.

The `stack` fixture starts a JWKS server standing in for Supabase Auth, the proxy
with the fake provider, the gateway, and the orchestrator, executor and grader
workers, all against the test Postgres and Redis. Tests act as signed-in users with
tokens signed by a local key, so nothing here calls Supabase or a model provider.

Each test signs up its own users (`...@e2e.test`), because the trial allows one
submission. The module deletes them when it ends.
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import ec
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from orqen_core import streams
from scripts import seed

from ..conftest import ROOT, TestSettings

pytestmark = pytest.mark.integration

PROBLEM = seed.sid("problem", seed.TENANT, seed.PROBLEM_SLUG)
TENANT = seed.sid("tenant", seed.TENANT)
PROMPT = "Extract vendor, date, total and currency as JSON."
KID = "e2e-key"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_http(url: str, proc: subprocess.Popen[bytes], timeout_s: float = 20) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{proc.args!r} exited with {proc.returncode}")
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(url)


@dataclass
class Stack:
    env: dict[str, str]
    logs: Path
    gateway_url: str
    issuer: str
    private_key: ec.EllipticCurvePrivateKey
    procs: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)

    def start(self, name: str, *args: str) -> subprocess.Popen[bytes]:
        log = (self.logs / f"{name}.log").open("ab")
        proc = subprocess.Popen(
            [sys.executable, *args], cwd=ROOT, env=self.env, stdout=log, stderr=log
        )
        self.procs[name] = proc
        return proc

    def worker(self, name: str) -> subprocess.Popen[bytes]:
        return self.start(name, "-m", "orqen_workers.cli", name)

    def kill(self, name: str) -> None:
        proc = self.procs.pop(name)
        proc.send_signal(signal.SIGKILL)
        proc.wait()

    def stop(self) -> None:
        for proc in self.procs.values():
            proc.terminate()
        for proc in self.procs.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def token(self, user_id: uuid.UUID, email: str, **claims: Any) -> str:
        body = {
            "sub": str(user_id),
            "email": email,
            "aud": "authenticated",
            "iss": self.issuer,
            "exp": int(time.time()) + 3600,
            "role": "authenticated",
        } | claims
        return jwt.encode(body, self.private_key, algorithm="ES256", headers={"kid": KID})


@pytest.fixture(scope="module")
def stack(
    seeded: AsyncEngine,
    cleanup: None,
    test_settings: TestSettings,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Stack]:
    root = tmp_path_factory.mktemp("stack")
    logs = root / "logs"
    logs.mkdir()

    # Supabase stand-in: a static JWKS at the path the gateway derives from the URL.
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwks_dir = root / "auth" / "auth" / "v1" / ".well-known"
    jwks_dir.mkdir(parents=True)
    (jwks_dir / "jwks.json").write_text(
        json.dumps({"keys": [jwk | {"kid": KID, "alg": "ES256", "use": "sig"}]})
    )

    jwks_port, proxy_port, gateway_port = free_port(), free_port(), free_port()
    supabase_url = f"http://127.0.0.1:{jwks_port}"
    env = {
        **os.environ,
        "ORQEN_DATABASE_URL": test_settings.test_database_url,
        "ORQEN_REDIS_URL": test_settings.test_redis_url,
        "ORQEN_SUPABASE_URL": supabase_url,
        "ORQEN_PROXY_URL": f"http://127.0.0.1:{proxy_port}",
        "ORQEN_PROVIDER": "fake",
        "ORQEN_CLAIM_IDLE_MS": "1500",
        "ORQEN_LOG_JSON": "true",
    }
    s = Stack(env, logs, f"http://127.0.0.1:{gateway_port}", f"{supabase_url}/auth/v1", key)

    async def reset_redis() -> None:
        redis = Redis.from_url(test_settings.test_redis_url)
        await redis.flushdb()
        await streams.ensure_groups(redis)
        await redis.aclose()

    asyncio.run(reset_redis())
    try:
        jwks = s.start(
            "jwks", "-m", "http.server", str(jwks_port), "-b", "127.0.0.1", "-d", str(root / "auth")
        )
        wait_http(f"{supabase_url}/auth/v1/.well-known/jwks.json", jwks)
        uvicorn = ("-m", "uvicorn", "--host", "127.0.0.1", "--port")
        proxy = s.start("proxy", *uvicorn, str(proxy_port), "orqen_proxy.app:app")
        gateway = s.start("gateway", *uvicorn, str(gateway_port), "orqen_gateway.app:app")
        wait_http(f"http://127.0.0.1:{proxy_port}/healthz", proxy)
        wait_http(f"{s.gateway_url}/healthz", gateway)
        for name in ("orchestrator", "executor", "grader"):
            s.worker(name)
        yield s
    finally:
        s.stop()
        for f in sorted(logs.iterdir()):
            print(f"--- {f.name}\n{f.read_text()[-3000:]}")


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def cleanup(seeded: AsyncEngine) -> AsyncIterator[None]:
    """Runs after `stack` stops, so no worker writes behind it."""
    yield
    who = "SELECT id FROM identity.users WHERE email LIKE '%@e2e.test'"
    async with seeded.begin() as c:
        for table in (
            "ops.llm_usage",
            "competition.practice_bests",
            "judging.submissions",
            "billing.subscriptions",
            "identity.memberships",
        ):
            await c.execute(text(f"DELETE FROM {table} WHERE user_id IN ({who})"))
        await c.execute(text(f"DELETE FROM identity.users WHERE id IN ({who})"))
        await c.execute(text("DELETE FROM auth.users WHERE email LIKE '%@e2e.test'"))


@dataclass
class User:
    id: uuid.UUID
    headers: dict[str, str]


async def sign_up(stack: Stack, engine: AsyncEngine, client: httpx.AsyncClient) -> User:
    """Create the Supabase side of a user, then the Orqen side through /v1/me."""
    user_id = uuid.uuid4()
    email = f"{user_id.hex[:12]}@e2e.test"
    async with engine.begin() as c:
        await c.execute(
            text("INSERT INTO auth.users (id, email) VALUES (:id, :email)"),
            {"id": user_id, "email": email},
        )
    headers = {"Authorization": f"Bearer {stack.token(user_id, email)}"}
    resp = await client.post("/v1/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return User(user_id, headers)


async def submit(
    client: httpx.AsyncClient, user: User, mode: str = "submit", prompt: str = PROMPT
) -> httpx.Response:
    return await client.post(
        "/v1/submissions",
        headers=user.headers,
        json={"problem_id": str(PROBLEM), "mode": mode, "prompt": prompt},
    )


async def finished(
    client: httpx.AsyncClient, user: User, submission_id: str, timeout_s: float = 45
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body: dict[str, Any] = (
            await client.get(f"/v1/submissions/{submission_id}", headers=user.headers)
        ).json()
        if body["status"] in ("COMPLETED", "FAILED", "TIMED_OUT"):
            return body
        await asyncio.sleep(0.2)
    raise TimeoutError(f"submission {submission_id} still {body['status']}")


@pytest_asyncio.fixture(loop_scope="session")
async def client(stack: Stack) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=stack.gateway_url, timeout=10) as c:
        yield c


def final_tests(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """The last event for each test: a retried test has earlier SYSTEM_ERROR rows."""
    finals: dict[int, dict[str, Any]] = {}
    for event in sorted(snapshot["events"], key=lambda e: e["seq"]):
        if event["type"] == "test":
            finals[event["test"]] = event
    return finals


async def scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as c:
        return (await c.execute(text(sql), params)).scalar()


# Auth ---------------------------------------------------------------------------------


async def test_requests_without_a_valid_token_are_refused(
    stack: Stack, client: httpx.AsyncClient
) -> None:
    assert (await client.post("/v1/me")).status_code == 401
    expired = stack.token(uuid.uuid4(), "x@e2e.test", exp=int(time.time()) - 60)
    resp = await client.post("/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


async def test_first_sign_in_creates_the_account_once(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    again = (await client.post("/v1/me", headers=user.headers)).json()
    assert again["role"] == "contestant"
    assert again["plan_id"] == "free_trial"
    assert again["subscription_status"] == "trialing"
    subs = await scalar(
        seeded, "SELECT count(*) FROM billing.subscriptions WHERE user_id = :u", u=user.id
    )
    assert subs == 1


async def test_submitting_before_sign_up_is_refused(
    stack: Stack, client: httpx.AsyncClient
) -> None:
    token = stack.token(uuid.uuid4(), "ghost@e2e.test")
    resp = await submit(client, User(uuid.uuid4(), {"Authorization": f"Bearer {token}"}))
    assert resp.status_code == 403


# The happy path ---------------------------------------------------------------------


async def test_a_submission_runs_every_hop_and_lands_on_the_leaderboard(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient, test_settings: TestSettings
) -> None:
    user = await sign_up(stack, seeded, client)
    redis = Redis.from_url(test_settings.test_redis_url)
    pubsub = redis.pubsub()
    await pubsub.psubscribe(f"t:{TENANT}:sub:*")
    try:
        resp = await submit(client, user)
        assert resp.status_code == 202, resp.text
        sid = resp.json()["submission_id"]
        body = await finished(client, user, sid)

        # Everything was published by now; drain it. A None can be a skipped
        # subscribe confirmation, so stop on the completed event or the deadline.
        seen: list[dict[str, Any]] = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(e["type"] == "completed" for e in seen):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and (event := json.loads(msg["data"]))["submission_id"] == sid:
                seen.append(event)
    finally:
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await redis.aclose()

    assert body["status"] == "COMPLETED"
    assert body["score"] == 100.0
    tests = final_tests(body)
    assert body["total_tests"] == len(seed.TESTS) == len(tests)
    assert {t["verdict"] for t in tests.values()} == {"PASS"}
    assert all(t["steps"] == 1 and t["tokens"] > 0 for t in tests.values())
    statuses = [e["status"] for e in body["events"] if e["type"] == "status"]
    assert statuses == ["EXPANDING", "RUNNING"]

    best = await scalar(
        seeded,
        "SELECT best_score FROM competition.practice_bests WHERE user_id = :u AND problem_id = :p",
        u=user.id,
        p=PROBLEM,
    )
    assert best == 100
    calls = await scalar(
        seeded,
        "SELECT count(*) FROM ops.llm_usage WHERE submission_id = :s AND cost_usd > 0",
        s=sid,
    )
    assert calls == len(seed.TESTS)
    assert await scalar(
        seeded,
        "SELECT cost_usd > 0 AND total_tokens > 0 FROM judging.submissions WHERE id = :s",
        s=sid,
    )

    # Events can arrive out of order across workers; `seq` is what lets a client sort them.
    seqs = [e["seq"] for e in seen]
    assert len(set(seqs)) == len(seqs)
    kinds = [e["type"] for e in seen]
    assert kinds.count("test") == len(seed.TESTS)
    assert kinds.count("completed") == 1


async def test_wrong_answers_score_only_the_gates_they_pass(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    resp = await submit(client, user, mode="run", prompt=f"{PROMPT} #fake:wrong")
    body = await finished(client, user, resp.json()["submission_id"])
    samples = sum(1 for _, _, is_sample in seed.TESTS if is_sample)
    tests = final_tests(body)
    assert len(tests) == samples
    assert {t["verdict"] for t in tests.values()} == {"FAIL"}
    assert {t["detail"] for t in tests.values()} == {"failed json_fields, numeric_tolerance"}
    assert body["score"] == pytest.approx(33.3)  # each test: 1 of 3 gates, stored as 0.333


async def test_provider_outages_are_retried_then_recorded(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    resp = await submit(client, user, mode="run", prompt=f"{PROMPT} #fake:error")
    body = await finished(client, user, resp.json()["submission_id"])
    assert {t["verdict"] for t in final_tests(body).values()} == {"SYSTEM_ERROR"}
    retries = [e for e in body["events"] if e["type"] == "test" and e["attempt"] < 3]
    assert len(retries) == 2 * len(final_tests(body))  # attempts 1 and 2, each its own row
    attempts = await scalar(
        seeded,
        "SELECT min(attempts) FROM judging.test_results WHERE submission_id = :s",
        s=body["submission_id"],
    )
    assert attempts == 3


# Plan limits over HTTP ---------------------------------------------------------------


async def test_plan_limits_come_back_as_402_and_429(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    for _ in range(10):
        assert (await submit(client, user, mode="run")).status_code == 202
    limited = await submit(client, user, mode="run")
    assert limited.status_code == 429
    assert "10 per hour" in limited.json()["detail"]

    assert (await submit(client, user)).status_code == 202
    assert (await submit(client, user)).status_code == 402


async def test_an_idempotency_key_returns_the_first_submission(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    body = {"problem_id": str(PROBLEM), "mode": "run", "prompt": PROMPT}
    headers = user.headers | {"Idempotency-Key": "retry-1"}
    first = await client.post("/v1/submissions", headers=headers, json=body)
    second = await client.post("/v1/submissions", headers=headers, json=body)
    assert (first.status_code, second.status_code) == (202, 200)
    assert first.json()["submission_id"] == second.json()["submission_id"]


# Crash recovery ---------------------------------------------------------------------


async def test_a_killed_executor_loses_no_work(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    resp = await submit(client, user, prompt=f"{PROMPT} #fake:slow=1")
    sid = resp.json()["submission_id"]

    # Wait until the executor has results in flight, then kill it without warning.
    deadline = time.monotonic() + 20
    while not await scalar(
        seeded, "SELECT count(*) FROM judging.test_results WHERE submission_id = :s", s=sid
    ):
        assert time.monotonic() < deadline, "no result arrived"
        await asyncio.sleep(0.1)
    stack.kill("executor")
    stack.worker("executor")

    body = await finished(client, user, sid, timeout_s=60)
    assert body["status"] == "COMPLETED"
    assert len(final_tests(body)) == len(seed.TESTS)
    assert body["score"] == 100.0
    reclaimed = (stack.logs / "executor.log").read_text().count("consumer.reclaimed")
    assert reclaimed > 0


# Reads and the live stream ------------------------------------------------------------


async def test_the_problem_set_shows_samples_but_never_hidden_tests(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    listed = (await client.get("/v1/problems", headers=user.headers)).json()
    assert [p["slug"] for p in listed] == [seed.PROBLEM_SLUG]
    problem = (await client.get(f"/v1/problems/{PROBLEM}", headers=user.headers)).json()
    samples = sum(1 for _, _, is_sample in seed.TESTS if is_sample)
    assert [s["ordinal"] for s in problem["samples"]] == list(range(1, samples + 1))
    assert problem["limits"]["models"] == [seed.MODEL]
    assert problem["my_best"] is None


async def test_the_event_stream_replays_then_follows_until_completed(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    user = await sign_up(stack, seeded, client)
    sid = (await submit(client, user, mode="run", prompt=f"{PROMPT} #fake:slow=0.3")).json()[
        "submission_id"
    ]
    seen: list[dict[str, Any]] = []
    async with client.stream(
        "GET", f"/v1/submissions/{sid}/events", headers=user.headers, timeout=30
    ) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                seen.append(json.loads(line[6:]))
    seqs = [e["seq"] for e in seen]
    assert seqs == sorted(set(seqs))
    assert seen[-1]["type"] == "completed"
    assert [e["type"] for e in seen].count("test") == 3

    # Resuming after the last seq replays nothing and ends at once: the run is over.
    async with client.stream(
        "GET",
        f"/v1/submissions/{sid}/events",
        headers=user.headers | {"Last-Event-ID": str(seqs[-1])},
    ) as resp:
        assert [line async for line in resp.aiter_lines() if line.startswith("data: ")] == []


async def test_another_users_submission_is_invisible(
    stack: Stack, seeded: AsyncEngine, client: httpx.AsyncClient
) -> None:
    owner, stranger = await sign_up(stack, seeded, client), await sign_up(stack, seeded, client)
    sid = (await submit(client, owner, mode="run")).json()["submission_id"]
    assert (await client.get(f"/v1/submissions/{sid}", headers=stranger.headers)).status_code == 404
    events = await client.get(f"/v1/submissions/{sid}/events", headers=stranger.headers)
    assert events.status_code == 404
