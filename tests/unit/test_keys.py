from uuid import uuid4

from orqen_core import keys


def test_tenant_owned_keys_are_prefixed_with_the_tenant() -> None:
    tid, sid = uuid4(), uuid4()
    for key in (
        keys.sub_status(tid, sid),
        keys.sub_remaining(tid, sid),
        keys.sub_seq(tid, sid),
        keys.sub_channel(tid, sid),
        keys.tenant_inflight(tid),
        keys.idempotency(tid, uuid4(), "k"),
        keys.leaderboard(tid, uuid4()),
    ):
        assert key.startswith(f"t:{tid}:")


def test_submission_keys_do_not_collide() -> None:
    tid, sid = uuid4(), uuid4()
    builders = [
        keys.sub_status,
        keys.sub_remaining,
        keys.sub_seq,
        keys.sub_channel,
    ]
    built = [b(tid, sid) for b in builders]
    assert len(set(built)) == len(built)
