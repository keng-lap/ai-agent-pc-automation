from pathlib import Path

import pytest

from agent_backend.durable_step_up import (
    DurableStepUpUnavailable,
    SQLiteStepUpStore,
)
from agent_backend.totp import code_at

SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
OWNER = "google-owner-sub"
SESSION = "session-1"
PLAN = "a" * 32
DIGEST = "b" * 64
NOW = 1_800_000_000.0


class TestSecureStorage:
    def prepare_database_path(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)

    def finalize_database_file(self, path: Path):
        assert path.is_file()


def make_store(tmp_path, now=None):
    return SQLiteStepUpStore(
        tmp_path / "private" / "step-up.sqlite3",
        secure_storage=TestSecureStorage(),
        clock=lambda: NOW if now is None else now[0],
    )


def wrong_code():
    valid = code_at(SECRET, NOW)
    return "000000" if valid != "000000" else "000001"


def create(store):
    return store.create(
        owner_sub=OWNER,
        session_id=SESSION,
        plan_id=PLAN,
        action_digest=DIGEST,
        risk_class="high",
    )


def consume(store, challenge, *, code=None, session=SESSION, plan=PLAN, digest=DIGEST):
    return store.verify_and_consume(
        challenge_id=challenge["challenge_id"],
        owner_sub=OWNER,
        session_id=session,
        plan_id=plan,
        action_digest=digest,
        risk_class="high",
        code=code or code_at(SECRET, NOW),
        secret_loader=lambda: SECRET,
    )


def test_challenge_and_replay_counter_survive_store_restart(tmp_path):
    first = make_store(tmp_path)
    challenge = create(first)
    assert consume(first, challenge)
    assert first.get_status(challenge["challenge_id"]) == "consumed"

    restarted = make_store(tmp_path)
    second_challenge = create(restarted)
    # The same TOTP step cannot be reused after reopening the database.
    assert not consume(restarted, second_challenge)
    assert restarted.get_status(second_challenge["challenge_id"]) == "active"


def test_only_exact_owner_session_and_action_can_consume(tmp_path):
    store = make_store(tmp_path)
    challenge = create(store)
    assert not consume(store, challenge, session="another-session")
    assert not consume(store, challenge, plan="c" * 32)
    assert store.get_status(challenge["challenge_id"]) == "invalidated"


def test_expired_challenge_is_persistently_expired(tmp_path):
    now = [NOW]
    store = make_store(tmp_path, now)
    challenge = create(store)
    now[0] += 121
    assert not consume(store, challenge)
    assert store.get_status(challenge["challenge_id"]) == "expired"



def test_challenge_expiring_while_waiting_for_database_lock_is_not_consumed(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    now = [NOW]
    clock_calls = [0]
    waiting_for_database_lock = Event()

    def clock():
        clock_calls[0] += 1
        if clock_calls[0] == 2:
            waiting_for_database_lock.set()
        return now[0]

    store = SQLiteStepUpStore(
        tmp_path / "private" / "step-up.sqlite3",
        secure_storage=TestSecureStorage(),
        clock=clock,
    )
    challenge = create(store)
    locker = store._connect()
    locker.execute("BEGIN IMMEDIATE")

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(consume, store, challenge)
            try:
                assert waiting_for_database_lock.wait(timeout=5)
                now[0] = challenge["expires_at"] + 1
            finally:
                locker.commit()
            assert not future.result(timeout=5)
    finally:
        locker.close()

    assert store.get_status(challenge["challenge_id"]) == "expired"


def test_challenge_expiring_while_secret_loads_is_not_consumed(tmp_path):
    now = [NOW]
    store = make_store(tmp_path, now)
    challenge = create(store)

    def load_secret():
        now[0] = challenge["expires_at"] + 1
        return SECRET

    assert not store.verify_and_consume(
        challenge_id=challenge["challenge_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        plan_id=PLAN,
        action_digest=DIGEST,
        risk_class="high",
        code=code_at(SECRET, NOW),
        secret_loader=load_secret,
    )
    assert store.get_status(challenge["challenge_id"]) == "expired"


def test_clock_rollback_while_secret_loads_invalidates_challenge(tmp_path):
    now = [NOW]
    store = make_store(tmp_path, now)
    challenge = create(store)

    def load_secret():
        now[0] -= 1
        return SECRET

    assert not store.verify_and_consume(
        challenge_id=challenge["challenge_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        plan_id=PLAN,
        action_digest=DIGEST,
        risk_class="high",
        code=code_at(SECRET, NOW),
        secret_loader=load_secret,
    )
    assert store.get_status(challenge["challenge_id"]) == "invalidated"


def test_invalid_codes_lock_challenge_after_five_attempts(tmp_path):
    store = make_store(tmp_path)
    challenge = create(store)
    for _ in range(5):
        assert not consume(store, challenge, code=wrong_code())
    assert store.get_status(challenge["challenge_id"]) == "locked"


def _run_concurrent_consumptions(stores, challenges):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(len(stores))

    def attempt(index):
        barrier.wait(timeout=5)
        return consume(stores[index], challenges[index])

    with ThreadPoolExecutor(max_workers=len(stores)) as pool:
        return list(pool.map(attempt, range(len(stores))))


def test_concurrent_same_challenge_across_store_instances_is_one_time(tmp_path):
    first = make_store(tmp_path)
    second = make_store(tmp_path)
    challenge = create(first)

    results = _run_concurrent_consumptions(
        [first, second],
        [challenge, challenge],
    )

    assert sum(results) == 1
    assert first.get_status(challenge["challenge_id"]) == "consumed"


def test_concurrent_distinct_challenges_cannot_reuse_same_totp_step(tmp_path):
    first = make_store(tmp_path)
    second = make_store(tmp_path)
    challenges = [create(first), create(second)]

    results = _run_concurrent_consumptions(
        [first, second],
        challenges,
    )

    assert sum(results) == 1
    assert sorted(
        store.get_status(challenge["challenge_id"])
        for store, challenge in zip([first, second], challenges, strict=True)
    ) == ["active", "consumed"]


def test_default_windows_storage_remains_fail_closed(monkeypatch, tmp_path):
    from agent_backend import durable_step_up
    from agent_backend.platform_storage import PlatformStorageUnavailable

    monkeypatch.setattr(
        durable_step_up,
        "create_platform_secure_storage",
        lambda: (_ for _ in ()).throw(
            PlatformStorageUnavailable("Windows storage unavailable")
        ),
    )
    with pytest.raises(DurableStepUpUnavailable, match="cannot be trusted"):
        SQLiteStepUpStore(tmp_path / "step-up.sqlite3")


def test_owner_session_failure_limit_survives_new_challenge_and_restart(tmp_path):
    first = make_store(tmp_path)
    challenge = create(first)
    for _ in range(5):
        assert not consume(first, challenge, code="000000")
    assert first.get_status(challenge["challenge_id"]) == "locked"

    restarted = make_store(tmp_path)
    next_challenge = create(restarted)
    assert not consume(restarted, next_challenge)
    assert restarted.get_status(next_challenge["challenge_id"]) == "locked"


def test_active_challenge_capacity_is_bounded(tmp_path):
    from agent_backend.durable_step_up import DurableStepUpConflict

    store = make_store(tmp_path)
    for _ in range(128):
        create(store)
    with pytest.raises(DurableStepUpConflict, match="capacity"):
        create(store)


def test_clock_rollback_invalidates_persisted_challenge(tmp_path):
    now = [NOW]
    store = make_store(tmp_path, now)
    challenge = create(store)
    now[0] -= 1
    assert not consume(store, challenge)
    assert store.get_status(challenge["challenge_id"]) == "invalidated"


def test_secret_loader_failure_does_not_consume_challenge(tmp_path):
    from agent_backend.durable_step_up import DurableStepUpUnavailable

    store = make_store(tmp_path)
    challenge = create(store)
    with pytest.raises(DurableStepUpUnavailable, match="secret could not be loaded"):
        store.verify_and_consume(
            challenge_id=challenge["challenge_id"],
            owner_sub=OWNER,
            session_id=SESSION,
            plan_id=PLAN,
            action_digest=DIGEST,
            risk_class="high",
            code=code_at(SECRET, NOW),
            secret_loader=lambda: (_ for _ in ()).throw(OSError("secret backend detail")),
        )
    assert store.get_status(challenge["challenge_id"]) == "active"
