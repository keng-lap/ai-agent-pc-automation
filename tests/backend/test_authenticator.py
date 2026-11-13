import base64
import json
import os

import pytest

from agent_backend.authenticator import (
    AuthenticatorEnrollmentManager,
    EncryptedTotpSecretFileStore,
    SecretStoreError,
    WindowsDpapiProtector,
)
from agent_backend.totp import code_at


class FakeProtector:
    """Non-cryptographic test double; production Windows adapter uses DPAPI."""

    def protect(self, plaintext: bytes) -> bytes:
        return b"test-protected:" + plaintext

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = b"test-protected:"
        if not ciphertext.startswith(prefix):
            raise ValueError("invalid protected payload")
        return ciphertext[len(prefix) :]


RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
NEW_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def build_manager(tmp_path, now=90):
    store = EncryptedTotpSecretFileStore(
        tmp_path / "private" / "authenticator.json",
        FakeProtector(),
    )
    manager = AuthenticatorEnrollmentManager(
        secret_store=store,
        clock=lambda: now,
        secret_factory=lambda: RFC_SECRET,
    )
    return manager, store


def test_secret_store_encrypts_before_writing_and_binds_owner(tmp_path):
    manager, store = build_manager(tmp_path)
    enrollment = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")
    payload = base64.b64decode(enrollment.qr_data_uri.split(",", 1)[1])
    assert enrollment.qr_data_uri.startswith("data:image/png;base64,")
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")

    # The QR response is one-time; persisted bytes contain only protector output.
    assert manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(RFC_SECRET, 90),
    )
    raw_file = store._path.read_text(encoding="ascii")
    assert "owner-sub" not in raw_file
    assert "otpauth://" not in raw_file
    assert store.load(owner_sub="owner-sub") is not None
    assert store.load(owner_sub="different-owner") is None


def test_enrollment_is_one_time_and_does_not_allow_self_service_replacement(tmp_path):
    manager, _store = build_manager(tmp_path)
    enrollment = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")
    code = code_at(RFC_SECRET, 90)

    assert manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="owner-sub",
        code=code,
    )
    with pytest.raises(RuntimeError, match="already enrolled"):
        manager.begin(owner_sub="owner-sub", account_name="owner@example.test")


def test_wrong_owner_cannot_confirm_enrollment(tmp_path):
    manager, _store = build_manager(tmp_path)
    enrollment = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")

    assert not manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="another-owner",
        code="123456",
    )


def test_invalid_totp_exhausts_five_enrollment_attempts(tmp_path):
    manager, _store = build_manager(tmp_path)
    enrollment = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")

    for _ in range(5):
        assert not manager.confirm(
            enrollment_id=enrollment.enrollment_id,
            owner_sub="owner-sub",
            code="000000",
        )
    assert not manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="owner-sub",
        code="000000",
    )


def test_expired_enrollment_cannot_be_confirmed(tmp_path):
    now = [90.0]
    store = EncryptedTotpSecretFileStore(tmp_path / "private" / "authenticator.json", FakeProtector())
    manager = AuthenticatorEnrollmentManager(
        secret_store=store,
        clock=lambda: now[0],
    )
    enrollment = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")
    now[0] = enrollment.expires_at

    assert not manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="owner-sub",
        code="000000",
    )


def test_secret_file_cannot_be_overwritten(tmp_path):
    store = EncryptedTotpSecretFileStore(tmp_path / "private" / "authenticator.json", FakeProtector())
    store.save(owner_sub="owner-sub", secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")

    with pytest.raises(SecretStoreError, match="already enrolled"):
        store.save(owner_sub="owner-sub", secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")


def test_recovery_replaces_secret_only_after_new_authenticator_is_confirmed(tmp_path):
    manager, store = build_manager(tmp_path, now=90)
    initial = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")
    assert manager.confirm(
        enrollment_id=initial.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(RFC_SECRET, 90),
    )

    manager._secret_factory = lambda: NEW_SECRET
    recovery = manager.begin_recovery(
        owner_sub="owner-sub",
        account_name="owner@example.test",
    )
    assert store.load(owner_sub="owner-sub") == RFC_SECRET
    assert not manager.confirm(
        enrollment_id=recovery.enrollment_id,
        owner_sub="owner-sub",
        code="000000",
    )
    assert store.load(owner_sub="owner-sub") == RFC_SECRET

    replacement = manager.begin_recovery(
        owner_sub="owner-sub",
        account_name="owner@example.test",
    )
    assert manager.confirm(
        enrollment_id=replacement.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(NEW_SECRET, 120),
    )
    assert store.load(owner_sub="owner-sub") == NEW_SECRET


def test_recovery_cannot_be_started_when_no_authenticator_is_enrolled(tmp_path):
    manager, _store = build_manager(tmp_path)

    with pytest.raises(RuntimeError, match="no authenticator"):
        manager.begin_recovery(
            owner_sub="owner-sub",
            account_name="owner@example.test",
        )


def test_corrupt_secret_file_fails_closed(tmp_path):
    store = EncryptedTotpSecretFileStore(tmp_path / "private" / "authenticator.json", FakeProtector())
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "authenticator.json").write_text(
        json.dumps({"version": 1, "ciphertext": "not-base64!"}),
        encoding="ascii",
    )

    with pytest.raises(SecretStoreError):
        store.load(owner_sub="owner-sub")


def test_dpapi_adapter_is_explicitly_windows_only():
    import os

    if os.name != "nt":
        with pytest.raises(SecretStoreError, match="Windows"):
            WindowsDpapiProtector().protect(b"test")





@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI integration test")
def test_windows_dpapi_protects_and_unprotects_secret_bytes():
    protector = WindowsDpapiProtector()
    plaintext = b"local authenticator secret material"

    protected = protector.protect(plaintext)

    assert protected != plaintext
    assert plaintext not in protected
    assert protector.unprotect(protected) == plaintext



def test_enrollment_expiry_uses_monotonic_time_after_wall_clock_rollback(tmp_path):
    wall_time = [100000.0]
    monotonic_time = [200.0]
    store = EncryptedTotpSecretFileStore(
        tmp_path / "private" / "authenticator.json",
        FakeProtector(),
    )
    manager = AuthenticatorEnrollmentManager(
        secret_store=store,
        clock=lambda: wall_time[0],
        monotonic_clock=lambda: monotonic_time[0],
        secret_factory=lambda: RFC_SECRET,
    )
    enrollment = manager.begin(
        owner_sub="owner-sub",
        account_name="owner@example.test",
    )

    wall_time[0] -= 86_400
    monotonic_time[0] += 300

    assert not manager.confirm(
        enrollment_id=enrollment.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(RFC_SECRET, 100000.0),
    )


def test_new_enrollment_replaces_an_abandoned_pending_qr(tmp_path):
    manager, store = build_manager(tmp_path, now=90)
    first = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")
    second = manager.begin(owner_sub="owner-sub", account_name="owner@example.test")

    assert first.enrollment_id != second.enrollment_id
    assert not manager.confirm(
        enrollment_id=first.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(RFC_SECRET, 90),
    )
    assert manager.confirm(
        enrollment_id=second.enrollment_id,
        owner_sub="owner-sub",
        code=code_at(RFC_SECRET, 90),
    )
    assert store.load(owner_sub="owner-sub") == RFC_SECRET


def test_dpapi_output_cleanup_releases_data_and_description_allocations(monkeypatch):
    from agent_backend import authenticator

    data_pointer = object()
    description_pointer = object()
    target = type("DataBlobStub", (), {"pbData": data_pointer})()
    freed = []

    class FakeCtypes:
        @staticmethod
        def cast(pointer, _pointer_type):
            return pointer

    class FakeKernel32:
        def LocalFree(self, pointer):
            freed.append(pointer)

    monkeypatch.setattr(authenticator, "ctypes", FakeCtypes)

    WindowsDpapiProtector._free_output_buffers(
        FakeKernel32(),
        target,
        description_pointer,
    )

    assert freed == [data_pointer, description_pointer]


def test_dpapi_output_cleanup_handles_missing_description_allocation(monkeypatch):
    from agent_backend import authenticator

    data_pointer = object()
    target = type("DataBlobStub", (), {"pbData": data_pointer})()
    freed = []

    class FakeCtypes:
        @staticmethod
        def cast(pointer, _pointer_type):
            return pointer

    class FakeKernel32:
        def LocalFree(self, pointer):
            freed.append(pointer)

    monkeypatch.setattr(authenticator, "ctypes", FakeCtypes)

    WindowsDpapiProtector._free_output_buffers(FakeKernel32(), target)

    assert freed == [data_pointer]
