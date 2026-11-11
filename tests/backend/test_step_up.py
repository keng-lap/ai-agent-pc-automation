import pytest

from agent_backend.step_up import (
    MAX_FAILED_ATTEMPTS,
    StepUpChallengeStore,
)
from agent_backend.totp import TotpReplayGuard, code_at

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
OWNER = "google-owner-sub"
SESSION = "session-123"
PLAN_ID = "a" * 32
DIGEST = "b" * 64


def build_store(now=90):
    return StepUpChallengeStore(
        replay_guard=TotpReplayGuard(),
        clock=lambda: now,
    )


def create(store, **changes):
    values = {
        "owner_sub": OWNER,
        "session_id": SESSION,
        "plan_id": PLAN_ID,
        "action_digest": DIGEST,
        "risk_class": "high",
    }
    values.update(changes)
    return store.create(**values)


def verify(store, receipt, **changes):
    values = {
        "challenge_id": receipt.challenge_id,
        "owner_sub": OWNER,
        "session_id": SESSION,
        "plan_id": PLAN_ID,
        "action_digest": DIGEST,
        "risk_class": "high",
        "secret": RFC_SECRET,
        "code": code_at(RFC_SECRET, 90),
    }
    values.update(changes)
    return store.verify_and_consume(**values)


def test_challenge_binds_owner_session_plan_digest_and_risk():
    store = build_store()
    receipt = create(store)

    assert verify(store, receipt) is True
    assert store.get(receipt.challenge_id).status == "consumed"


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_sub": "another-owner"},
        {"session_id": "another-session"},
    ],
)
def test_wrong_owner_or_session_cannot_consume_challenge(changes):
    store = build_store()
    receipt = create(store)

    assert verify(store, receipt, **changes) is False
    assert store.get(receipt.challenge_id).status == "active"


@pytest.mark.parametrize(
    "changes",
    [
        {"plan_id": "c" * 32},
        {"action_digest": "d" * 64},
        {"risk_class": "low"},
    ],
)
def test_changed_action_binding_invalidates_challenge(changes):
    store = build_store()
    receipt = create(store)

    assert verify(store, receipt, **changes) is False
    assert store.get(receipt.challenge_id).status == "invalidated"


def test_non_high_risk_challenge_is_rejected():
    store = build_store()

    with pytest.raises(ValueError, match="high-risk"):
        create(store, risk_class="low")


def test_expired_challenge_fails_closed():
    now = [90.0]
    store = StepUpChallengeStore(clock=lambda: now[0])
    receipt = create(store)
    now[0] += 120

    assert verify(store, receipt) is False
    assert store.get(receipt.challenge_id).status == "expired"


def test_wrong_totp_locks_challenge_after_five_attempts():
    store = build_store()
    receipt = create(store)

    for _ in range(MAX_FAILED_ATTEMPTS):
        assert verify(store, receipt, code="000000") is False

    challenge = store.get(receipt.challenge_id)
    assert challenge.failed_attempts == MAX_FAILED_ATTEMPTS
    assert challenge.status == "locked"
    assert verify(store, receipt) is False


def test_successful_challenge_cannot_be_reused():
    store = build_store()
    receipt = create(store)

    assert verify(store, receipt) is True
    assert verify(store, receipt) is False


def test_same_totp_step_cannot_authorize_a_second_challenge():
    store = build_store()
    first = create(store)
    second = create(store)

    assert verify(store, first) is True
    assert verify(store, second) is False
    assert store.get(second.challenge_id).failed_attempts == 1


def test_concurrent_verification_consumes_challenge_once():
    from concurrent.futures import ThreadPoolExecutor

    store = build_store()
    receipt = create(store)

    def attempt():
        return verify(store, receipt)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: attempt(), range(8)))

    assert sum(results) == 1


def test_challenge_capacity_is_bounded():
    store = StepUpChallengeStore(clock=lambda: 90.0, capacity=1)
    create(store)

    with pytest.raises(RuntimeError, match="capacity"):
        create(store)



def test_failed_attempts_are_rate_limited_across_challenges_for_one_session():
    now = [90.0]
    store = StepUpChallengeStore(clock=lambda: now[0])

    for _ in range(MAX_FAILED_ATTEMPTS):
        receipt = create(store)
        assert verify(store, receipt, code="000000") is False

    final = create(store)
    assert verify(store, final) is False
    assert store.get(final.challenge_id).status == "locked"



def test_challenge_expiry_uses_monotonic_time_after_wall_clock_rollback():
    wall_time = [90.0]
    monotonic_time = [500.0]
    store = StepUpChallengeStore(
        clock=lambda: wall_time[0],
        monotonic_clock=lambda: monotonic_time[0],
    )
    receipt = create(store)

    wall_time[0] -= 86_400
    monotonic_time[0] += 120

    assert verify(store, receipt) is False
    assert store.get(receipt.challenge_id).status == "expired"


def test_totp_failure_window_does_not_reset_after_wall_clock_rollback():
    wall_time = [90.0]
    monotonic_time = [500.0]
    store = StepUpChallengeStore(
        clock=lambda: wall_time[0],
        monotonic_clock=lambda: monotonic_time[0],
    )

    for _ in range(MAX_FAILED_ATTEMPTS):
        receipt = create(store)
        assert verify(store, receipt, code="000000") is False

    wall_time[0] -= 86_400
    receipt = create(store)
    assert verify(store, receipt, code=code_at(RFC_SECRET, wall_time[0])) is False
    assert store.get(receipt.challenge_id).status == "locked"


def test_owner_session_failure_window_resets_after_five_minutes():
    now = [90.0]
    store = StepUpChallengeStore(clock=lambda: now[0])
    receipt = create(store)

    assert verify(store, receipt, code="000000") is False
    now[0] += 300
    next_receipt = create(store)

    assert store.verify_and_consume(
        challenge_id=next_receipt.challenge_id,
        owner_sub=OWNER,
        session_id=SESSION,
        plan_id=PLAN_ID,
        action_digest=DIGEST,
        risk_class="high",
        secret=RFC_SECRET,
        code=code_at(RFC_SECRET, now[0]),
    ) is True
