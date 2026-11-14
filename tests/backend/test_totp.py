import pytest

from agent_backend.totp import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    TotpConfigurationError,
    TotpReplayGuard,
    code_at,
    generate_secret,
    matching_step,
    provisioning_uri,
)

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_code_at_matches_rfc_6238_sha1_vectors(timestamp, expected):
    assert code_at(RFC_SECRET, timestamp) == expected


def test_generated_secret_is_random_base32_and_has_at_least_160_bits():
    first = generate_secret()
    second = generate_secret()

    assert first != second
    assert len(first) == 32
    assert all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in first)


def test_provisioning_uri_uses_standard_authenticator_parameters():
    uri = provisioning_uri(
        RFC_SECRET,
        account_name="owner@example.test",
        issuer="AI Agent PC",
    )
    assert uri.startswith("otpauth://totp/AI%20Agent%20PC%3Aowner%40example.test?")
    assert f"secret={RFC_SECRET}" in uri
    assert "issuer=AI%20Agent%20PC" in uri
    assert "algorithm=SHA1" in uri
    assert f"digits={TOTP_DIGITS}" in uri
    assert f"period={TOTP_PERIOD_SECONDS}" in uri


@pytest.mark.parametrize(
    "secret",
    ["", "not-a-secret", "ABC", "A" * 129, "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJ!"],
)
def test_invalid_secrets_are_rejected(secret):
    with pytest.raises(TotpConfigurationError):
        code_at(secret, 59)


@pytest.mark.parametrize("timestamp", [-1, float("nan"), float("inf"), True, "59"])
def test_invalid_timestamps_are_rejected(timestamp):
    with pytest.raises((TypeError, ValueError)):
        code_at(RFC_SECRET, timestamp)


def test_matching_step_accepts_current_and_one_adjacent_step_only():
    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, 60), timestamp=59) == 2
    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, 30), timestamp=59) == 1
    assert matching_step(RFC_SECRET, code_at(RFC_SECRET, 0), timestamp=59) == 0


@pytest.mark.parametrize("code", ["12345", "1234567", "１２３４５６", "12a456", ""])
def test_matching_step_rejects_malformed_codes(code):
    assert matching_step(RFC_SECRET, code, timestamp=59) is None


def test_replay_guard_consumes_a_matching_step_once():
    guard = TotpReplayGuard()
    code = code_at(RFC_SECRET, 90)

    assert guard.verify_and_consume(
        owner_key="google-sub-owner", secret=RFC_SECRET, code=code, timestamp=90
    )
    assert not guard.verify_and_consume(
        owner_key="google-sub-owner", secret=RFC_SECRET, code=code, timestamp=90
    )


def test_replay_guard_rejects_a_previously_consumed_adjacent_step():
    guard = TotpReplayGuard()
    previous = code_at(RFC_SECRET, 60)

    assert guard.verify_and_consume(
        owner_key="owner", secret=RFC_SECRET, code=previous, timestamp=90
    )
    assert not guard.verify_and_consume(
        owner_key="owner", secret=RFC_SECRET, code=previous, timestamp=90
    )


def test_replay_guard_is_scoped_to_owner():
    guard = TotpReplayGuard()
    code = code_at(RFC_SECRET, 90)

    assert guard.verify_and_consume(
        owner_key="owner-a", secret=RFC_SECRET, code=code, timestamp=90
    )
    assert guard.verify_and_consume(
        owner_key="owner-b", secret=RFC_SECRET, code=code, timestamp=90
    )


def test_replay_guard_rejects_invalid_owner_or_code():
    guard = TotpReplayGuard()

    assert not guard.verify_and_consume(
        owner_key="", secret=RFC_SECRET, code=code_at(RFC_SECRET, 90), timestamp=90
    )
    assert not guard.verify_and_consume(
        owner_key="owner", secret=RFC_SECRET, code="000000", timestamp=90
    )


def test_replay_guard_serializes_concurrent_reuse():
    from concurrent.futures import ThreadPoolExecutor

    guard = TotpReplayGuard()
    code = code_at(RFC_SECRET, 90)

    def attempt():
        return guard.verify_and_consume(
            owner_key="owner", secret=RFC_SECRET, code=code, timestamp=90
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: attempt(), range(8)))

    assert sum(results) == 1



def test_replay_guard_blocks_current_time_step_after_restart():
    now = [90.0]
    guard = TotpReplayGuard(clock=lambda: now[0])
    guard.block_through_current_step(owner_key="master-user", timestamp=now[0])

    assert not guard.verify_and_consume(
        owner_key="master-user",
        secret=RFC_SECRET,
        code=code_at(RFC_SECRET, now[0]),
        timestamp=now[0],
    )

    now[0] = 120.0
    assert guard.verify_and_consume(
        owner_key="master-user",
        secret=RFC_SECRET,
        code=code_at(RFC_SECRET, now[0]),
        timestamp=now[0],
    )


def test_replay_guard_rejects_invalid_restart_timestamp():
    guard = TotpReplayGuard(clock=lambda: 90.0)

    with pytest.raises(TotpConfigurationError):
        guard.block_through_current_step(
            owner_key="master-user",
            timestamp=float("nan"),
        )


def test_step_up_secret_loader_observes_secret_replaced_under_replay_lock():
    old_secret = RFC_SECRET
    new_secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    active_secret = [old_secret]
    guard = TotpReplayGuard()

    # Recovery commits the replacement and its matched step under the same
    # lock used by Step-up's secret loader and replay verification.
    assert guard.consume_step_after(
        owner_key="owner",
        step=4,
        action=lambda: active_secret.__setitem__(0, new_secret),
    )

    assert not guard.verify_and_consume_with_secret_loader(
        owner_key="owner",
        secret_loader=lambda: active_secret[0],
        code=code_at(old_secret, 180),
        timestamp=180,
    )
    assert guard.verify_and_consume_with_secret_loader(
        owner_key="owner",
        secret_loader=lambda: active_secret[0],
        code=code_at(new_secret, 180),
        timestamp=180,
    )
