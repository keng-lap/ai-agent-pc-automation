import base64
import json
from types import SimpleNamespace

import pytest

from agent_backend import platform_authenticator as module
from agent_backend.platform_authenticator import (
    PlatformAuthenticatorError,
    PlatformAuthenticatorManager,
    PlatformCredential,
    PlatformCredentialStore,
)


class FakeProtector:
    """Test protector that provides authenticated encryption like the DPAPI adapter."""

    def __init__(self) -> None:
        from cryptography.fernet import Fernet

        self._fernet = Fernet(base64.urlsafe_b64encode(bytes(range(32))))

    def protect(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)


OWNER = "master-google-sub"
SESSION = "session-identifier-123456"
CREDENTIAL_ID = b"registered-platform-credential"
PUBLIC_KEY = b"verified-public-key"


def build_manager(tmp_path, *, clock=None):
    store = PlatformCredentialStore(tmp_path / "private" / "platform.json", FakeProtector())
    manager = PlatformAuthenticatorManager(
        credential_store=store,
        rp_id="localhost",
        expected_origin="http://localhost:4200",
        clock=clock,
    )
    return manager, store


def install_fake_registration_verifier(monkeypatch, captured):
    monkeypatch.setattr(
        module,
        "generate_registration_options",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(module, "options_to_json", lambda _options: json.dumps({
        "challenge": "challenge",
        "authenticatorSelection": {
            "authenticatorAttachment": "platform",
            "userVerification": "required",
        },
    }))
    monkeypatch.setattr(
        module,
        "verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=CREDENTIAL_ID,
            credential_public_key=PUBLIC_KEY,
            sign_count=0,
        ),
    )


def test_registration_requests_platform_authenticator_and_required_verification(
    tmp_path, monkeypatch
):
    manager, store = build_manager(tmp_path)
    captured = {}
    install_fake_registration_verifier(monkeypatch, captured)

    options = manager.begin_registration(owner_sub=OWNER, session_id=SESSION)

    assert options["public_key"]["authenticatorSelection"] == {
        "authenticatorAttachment": "platform",
        "userVerification": "required",
    }
    assert captured["rp_id"] == "localhost"
    assert captured["authenticator_selection"].authenticator_attachment.value == "platform"
    assert captured["authenticator_selection"].user_verification.value == "required"

    manager.complete_registration(
        ceremony_id=options["ceremony_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        credential={"id": "credential", "authenticatorAttachment": "platform"},
    )
    assert store.load(owner_sub=OWNER) == PlatformCredential(
        OWNER, CREDENTIAL_ID, PUBLIC_KEY, 0
    )


def test_registration_challenge_is_bound_to_session_and_remains_usable_after_mismatch(
    tmp_path, monkeypatch
):
    manager, store = build_manager(tmp_path)
    captured = {}
    install_fake_registration_verifier(monkeypatch, captured)
    options = manager.begin_registration(owner_sub=OWNER, session_id=SESSION)
    response = {"id": "credential", "authenticatorAttachment": "platform"}

    with pytest.raises(PlatformAuthenticatorError):
        manager.complete_registration(
            ceremony_id=options["ceremony_id"],
            owner_sub=OWNER,
            session_id="another-session-identifier",
            credential=response,
        )
    manager.complete_registration(
        ceremony_id=options["ceremony_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        credential=response,
    )
    assert store.load(owner_sub=OWNER) is not None


def test_registration_challenge_is_one_time(tmp_path, monkeypatch):
    manager, _store = build_manager(tmp_path)
    install_fake_registration_verifier(monkeypatch, {})
    options = manager.begin_registration(owner_sub=OWNER, session_id=SESSION)
    response = {"id": "credential", "authenticatorAttachment": "platform"}

    manager.complete_registration(
        ceremony_id=options["ceremony_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        credential=response,
    )
    with pytest.raises(PlatformAuthenticatorError):
        manager.complete_registration(
            ceremony_id=options["ceremony_id"],
            owner_sub=OWNER,
            session_id=SESSION,
            credential=response,
        )


def test_assertion_requires_existing_owner_credential_and_required_uv(
    tmp_path, monkeypatch
):
    manager, store = build_manager(tmp_path)
    store.save_new(PlatformCredential(OWNER, CREDENTIAL_ID, PUBLIC_KEY, 0))
    captured = {}
    monkeypatch.setattr(
        module,
        "generate_authentication_options",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(module, "options_to_json", lambda _options: json.dumps({
        "challenge": "challenge",
        "userVerification": "required",
    }))
    monkeypatch.setattr(
        module,
        "verify_authentication_response",
        lambda **kwargs: SimpleNamespace(user_verified=True, new_sign_count=0),
    )

    options = manager.begin_assertion(
        owner_sub=OWNER, session_id=SESSION, purpose="recovery"
    )
    assert options["public_key"]["userVerification"] == "required"
    assert captured["allow_credentials"][0].id == CREDENTIAL_ID

    credential_response = {
        "id": base64.urlsafe_b64encode(CREDENTIAL_ID).rstrip(b"=").decode("ascii")
    }
    manager.complete_assertion(
        ceremony_id=options["ceremony_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="recovery",
        credential_response=credential_response,
    )
    assert store.load(owner_sub=OWNER).sign_count == 0


def test_assertion_challenge_is_bound_to_purpose_and_replay_protected(
    tmp_path, monkeypatch
):
    manager, store = build_manager(tmp_path)
    store.save_new(PlatformCredential(OWNER, CREDENTIAL_ID, PUBLIC_KEY, 0))
    monkeypatch.setattr(
        module,
        "generate_authentication_options",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(module, "options_to_json", lambda _options: "{}")
    monkeypatch.setattr(
        module,
        "verify_authentication_response",
        lambda **_kwargs: SimpleNamespace(user_verified=True, new_sign_count=0),
    )
    options = manager.begin_assertion(
        owner_sub=OWNER, session_id=SESSION, purpose="recovery"
    )
    response = {
        "id": base64.urlsafe_b64encode(CREDENTIAL_ID).rstrip(b"=").decode("ascii")
    }

    with pytest.raises(PlatformAuthenticatorError):
        manager.complete_assertion(
            ceremony_id=options["ceremony_id"],
            owner_sub=OWNER,
            session_id=SESSION,
            purpose="enrollment",
            credential_response=response,
        )
    manager.complete_assertion(
        ceremony_id=options["ceremony_id"],
        owner_sub=OWNER,
        session_id=SESSION,
        purpose="recovery",
        credential_response=response,
    )
    with pytest.raises(PlatformAuthenticatorError):
        manager.complete_assertion(
            ceremony_id=options["ceremony_id"],
            owner_sub=OWNER,
            session_id=SESSION,
            purpose="recovery",
            credential_response=response,
        )


def test_expired_challenge_fails_closed(tmp_path, monkeypatch):
    now = [10.0]
    manager, _store = build_manager(tmp_path, clock=lambda: now[0])
    install_fake_registration_verifier(monkeypatch, {})
    options = manager.begin_registration(owner_sub=OWNER, session_id=SESSION)
    now[0] += 121

    with pytest.raises(PlatformAuthenticatorError):
        manager.complete_registration(
            ceremony_id=options["ceremony_id"],
            owner_sub=OWNER,
            session_id=SESSION,
            credential={"id": "credential", "authenticatorAttachment": "platform"},
        )


def test_credential_store_encrypts_owner_and_rejects_corruption(tmp_path):
    store = PlatformCredentialStore(tmp_path / "private" / "platform.json", FakeProtector())
    credential = PlatformCredential(OWNER, CREDENTIAL_ID, PUBLIC_KEY, 4)
    store.save_new(credential)

    raw = store._path.read_bytes()
    assert OWNER.encode() not in raw
    assert store.load(owner_sub=OWNER) == credential
    assert store.load(owner_sub="another-owner") is None
    with pytest.raises(PlatformAuthenticatorError):
        store.save_new(credential)

    store._path.write_bytes(b"not-protected")
    with pytest.raises(PlatformAuthenticatorError):
        store.load(owner_sub=OWNER)


def test_only_localhost_origin_is_accepted(tmp_path):
    store = PlatformCredentialStore(tmp_path / "private" / "platform.json", FakeProtector())
    with pytest.raises(ValueError):
        PlatformAuthenticatorManager(
            credential_store=store,
            rp_id="127.0.0.1",
            expected_origin="http://127.0.0.1:4200",
        )
