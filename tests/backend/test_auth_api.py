import os
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_backend.auth_api import (
    SESSION_COOKIE_NAME,
    AuthServices,
)
from agent_backend.authenticator import (
    AuthenticatorEnrollmentManager,
    EncryptedTotpSecretFileStore,
)
from agent_backend.config import load_settings
from agent_backend.oidc import (
    ApplicationSessionStore,
    GoogleIdentity,
    LoginStart,
    MasterUserAllowlist,
)
from agent_backend.step_up import StepUpChallengeStore
from agent_backend.totp import TotpReplayGuard, code_at

OWNER = "stable-google-sub"
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
NEW_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
NOW = 1_800_000_000.0
HEADERS = {
    "origin": "http://127.0.0.1:4200",
    "x-local-agent-token": "a" * 64,
}


class FakeProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"test-protected:" + plaintext

    def unprotect(self, ciphertext: bytes) -> bytes:
        prefix = b"test-protected:"
        if not ciphertext.startswith(prefix):
            raise ValueError("invalid test payload")
        return ciphertext[len(prefix) :]


class FakeOidc:
    def __init__(self, identity=None):
        self.identity = identity or GoogleIdentity(
            sub=OWNER,
            email="owner@example.test",
        )
        self.completed = []

    def begin_login(self, *, require_recent_auth=False):
        self.require_recent_auth = require_recent_auth
        return LoginStart(authorization_url="https://accounts.google.com/test-login")

    def complete_login(self, *, state, code):
        self.completed.append((state, code))
        return self.identity


def build_client(tmp_path, *, identity=None):
    now = [NOW]
    settings = replace(
        load_settings(load_env_file=False),
        google_oidc_client_id="test-client-id",
        google_oidc_client_secret="test-client-secret",
        google_oidc_redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        master_google_sub=OWNER,
        app_session_ttl_seconds=1800,
        authenticator_secret_path=tmp_path / "private" / "authenticator.json",
    )
    replay_guard = TotpReplayGuard(clock=lambda: now[0])
    secret_store = EncryptedTotpSecretFileStore(
        settings.authenticator_secret_path,
        FakeProtector(),
    )
    allowlist = MasterUserAllowlist(OWNER)
    services = AuthServices(
        oidc=FakeOidc(identity),
        allowlist=allowlist,
        sessions=ApplicationSessionStore(
            ttl_seconds=1800,
            clock=lambda: now[0],
            monotonic_clock=lambda: now[0],
        ),
        secret_store=secret_store,
        enrollment=AuthenticatorEnrollmentManager(
            secret_store=secret_store,
            replay_guard=replay_guard,
            clock=lambda: now[0],
            secret_factory=lambda: RFC_SECRET,
        ),
        step_up=StepUpChallengeStore(
            replay_guard=replay_guard,
            clock=lambda: now[0],
        ),
    )
    from agent_backend.main import create_app

    client = TestClient(
        create_app(settings, auth_services=services),
        base_url="http://127.0.0.1:8000",
        headers=HEADERS,
    )
    return client, services, now


def sign_in(client, services, *, recently_authenticated=False):
    identity = GoogleIdentity(
        sub=OWNER,
        email="owner@example.test",
        recently_authenticated=recently_authenticated,
    )
    credential = services.sessions.create(
        identity=identity,
        allowlist=services.allowlist,
    )
    client.cookies.set(SESSION_COOKIE_NAME, credential.token)
    return credential


def test_auth_session_is_disabled_without_google_configuration(tmp_path):
    from agent_backend.main import create_app

    client = TestClient(
        create_app(load_settings(load_env_file=False)),
        base_url="http://127.0.0.1:8000",
        headers=HEADERS,
    )
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "authenticated": False,
        "authenticator_enrolled": False,
        "authenticator_storage_available": False,
    }


def test_google_callback_creates_http_only_master_session(tmp_path):
    client, services, _now = build_client(tmp_path)

    response = client.get(
        "/auth/google/callback?state=valid-state&code=valid-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["location"] == "http://127.0.0.1:4200/?login=success"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie
    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert services.oidc.completed == [("valid-state", "valid-code")]


def test_google_callback_rejects_non_master_identity(tmp_path):
    client, _services, _now = build_client(
        tmp_path,
        identity=GoogleIdentity(sub="other-sub", email="owner@example.test"),
    )

    response = client.get(
        "/auth/google/callback?state=valid-state&code=valid-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("?login=failed")
    assert "set-cookie" not in response.headers


def test_login_start_returns_only_google_authorization_url(tmp_path):
    client, _services, _now = build_client(tmp_path)

    response = client.get("/api/auth/google/start")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "authorization_url": "https://accounts.google.com/test-login"
    }


def test_reauthentication_start_requires_existing_session_and_requests_fresh_google_auth(tmp_path):
    client, services, _now = build_client(tmp_path)

    denied = client.get("/api/auth/google/reauth/start")
    assert denied.status_code == 401

    sign_in(client, services)
    response = client.get("/api/auth/google/reauth/start")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["authorization_url"] == "https://accounts.google.com/test-login"
    assert services.oidc.require_recent_auth is True


def test_fresh_google_callback_rotates_previous_owner_sessions(tmp_path):
    client, services, _now = build_client(
        tmp_path,
        identity=GoogleIdentity(
            sub=OWNER,
            email="owner@example.test",
            recently_authenticated=True,
        ),
    )
    previous = sign_in(client, services)

    response = client.get(
        "/auth/google/callback?state=fresh-state&code=fresh-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert services.sessions.resolve(previous.token) is None
    assert client.get("/api/auth/session").json()["authenticated"] is True


def test_api_routes_require_master_session_when_auth_is_enabled(tmp_path):
    client, _services, _now = build_client(tmp_path)

    response = client.post(
        "/api/plans",
        json={"request": "Install Google Chrome", "language": "en"},
    )

    assert response.status_code == 401


def test_authenticator_enrollment_and_confirmation_are_one_time(tmp_path):
    client, services, now = build_client(tmp_path)
    original_session = sign_in(client, services, recently_authenticated=True)

    start = client.post("/api/authenticator/enrollment", json={})
    assert start.status_code == 200
    assert start.headers["cache-control"] == "no-store"
    assert start.json()["qr_data_uri"].startswith("data:image/png;base64,")

    confirmed = client.post(
        "/api/authenticator/enrollment/confirm",
        json={
            "enrollment_id": start.json()["enrollment_id"],
            "code": code_at(RFC_SECRET, now[0]),
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {"enrolled": True}
    assert services.sessions.resolve(original_session.token) is None
    assert client.cookies.get(SESSION_COOKIE_NAME, domain="127.0.0.1", path="/") != original_session.token
    assert client.get("/api/authenticator/status").json()["authenticator_enrolled"] is True

    second = client.post("/api/authenticator/enrollment", json={})
    assert second.status_code == 409



def test_totp_enrollment_requires_recent_google_reauthentication(tmp_path):
    client, services, now = build_client(tmp_path)
    sign_in(client, services, recently_authenticated=True)
    now[0] += 301

    response = client.post("/api/authenticator/enrollment", json={})

    assert response.status_code == 403
    assert response.json() == {"detail": "Fresh Google sign-in required."}
    assert services.secret_store.is_configured() is False


def test_secret_store_failure_does_not_lock_owner_out_of_dashboard(tmp_path, monkeypatch):
    from agent_backend.authenticator import SecretStoreError

    client, services, _now = build_client(tmp_path)
    sign_in(client, services)

    def unavailable(*, owner_sub):
        raise SecretStoreError("simulated storage failure")

    monkeypatch.setattr(services.secret_store, "load", unavailable)
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "authenticated": True,
        "authenticator_enrolled": False,
        "authenticator_storage_available": False,
    }


def test_totp_recovery_replaces_lost_authenticator_after_google_reauth(tmp_path):
    client, services, now = build_client(
        tmp_path,
        identity=GoogleIdentity(
            sub=OWNER,
            email="owner@example.test",
            recently_authenticated=True,
        ),
    )
    sign_in(client, services, recently_authenticated=True)
    initial = client.post("/api/authenticator/enrollment", json={}).json()
    assert client.post(
        "/api/authenticator/enrollment/confirm",
        json={
            "enrollment_id": initial["enrollment_id"],
            "code": code_at(RFC_SECRET, now[0]),
        },
    ).status_code == 200
    assert services.secret_store.load(owner_sub=OWNER) == RFC_SECRET

    # The existing TOTP is treated as lost; Google OIDC is the recovery proof.
    assert client.get("/api/auth/google/reauth/start").status_code == 200
    callback = client.get(
        "/auth/google/callback?state=recovery-state&code=recovery-code",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert client.get("/api/auth/session").json()["authenticated"] is True

    services.enrollment._secret_factory = lambda: NEW_SECRET
    start = client.post("/api/authenticator/recovery", json={})
    assert start.status_code == 200
    assert start.headers["cache-control"] == "no-store"
    assert services.secret_store.load(owner_sub=OWNER) == RFC_SECRET

    confirmed = client.post(
        "/api/authenticator/recovery/confirm",
        json={
            "enrollment_id": start.json()["enrollment_id"],
            "code": code_at(NEW_SECRET, now[0] + 30),
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {"enrolled": True}
    assert services.secret_store.load(owner_sub=OWNER) == NEW_SECRET
    assert client.get("/api/auth/session").json() == {
        "enabled": True,
        "authenticated": True,
        "authenticator_enrolled": True,
        "authenticator_storage_available": True,
    }
    rotated_token = client.cookies.get(SESSION_COOKIE_NAME, domain="127.0.0.1", path="/")
    rotated_principal = services.sessions.resolve(rotated_token)
    assert rotated_principal is not None
    assert not services.sessions.is_recently_authenticated(
        rotated_principal,
        max_age_seconds=300,
    )


def test_corrupt_authenticator_storage_can_be_recovered_without_blocking_dashboard(tmp_path):
    client, services, now = build_client(
        tmp_path,
        identity=GoogleIdentity(
            sub=OWNER,
            email="owner@example.test",
            recently_authenticated=True,
        ),
    )
    if os.name == "nt":
        from agent_backend.windows_secret_storage import WindowsSecretFile

        WindowsSecretFile(services.secret_store._path).create_exclusive(
            b"{corrupt-secret-envelope"
        )
    else:
        services.secret_store._path.parent.mkdir(parents=True, exist_ok=True)
        services.secret_store._path.write_text(
            "{corrupt-secret-envelope",
            encoding="ascii",
        )
    sign_in(client, services)

    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
    assert session.json()["authenticator_storage_available"] is False

    assert client.get("/api/auth/google/reauth/start").status_code == 200
    callback = client.get(
        "/auth/google/callback?state=repair-state&code=repair-code",
        follow_redirects=False,
    )
    assert callback.status_code == 303

    services.enrollment._secret_factory = lambda: NEW_SECRET
    start = client.post("/api/authenticator/recovery", json={})
    assert start.status_code == 200
    confirmed = client.post(
        "/api/authenticator/recovery/confirm",
        json={
            "enrollment_id": start.json()["enrollment_id"],
            "code": code_at(NEW_SECRET, now[0] + 30),
        },
    )
    assert confirmed.status_code == 200
    assert services.secret_store.load(owner_sub=OWNER) == NEW_SECRET
    assert client.get("/api/auth/session").json()["authenticator_storage_available"] is True


def test_fresh_google_auth_grant_is_consumed_once_for_enrollment(tmp_path):
    client, services, _now = build_client(tmp_path)
    sign_in(client, services, recently_authenticated=True)

    first = client.post("/api/authenticator/enrollment", json={})
    second = client.post("/api/authenticator/enrollment", json={})

    assert first.status_code == 200
    assert second.status_code == 403
    assert services.secret_store.is_configured() is False


def test_totp_not_enrolled_does_not_block_google_dashboard_session(tmp_path):
    client, services, _now = build_client(tmp_path)
    sign_in(client, services)

    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "authenticated": True,
        "authenticator_enrolled": False,
        "authenticator_storage_available": True,
    }


def test_plan_approval_requires_fresh_totp_bound_to_exact_plan(tmp_path, monkeypatch):
    from agent_backend import plan_api
    from agent_backend.tools import ToolResult

    client, services, now = build_client(tmp_path)
    sign_in(client, services, recently_authenticated=True)
    enrollment = client.post("/api/authenticator/enrollment", json={}).json()
    assert client.post(
        "/api/authenticator/enrollment/confirm",
        json={
            "enrollment_id": enrollment["enrollment_id"],
            "code": code_at(RFC_SECRET, now[0]),
        },
    ).status_code == 200

    # Enrollment consumed this TOTP time-step; approval must use a fresh step.
    now[0] += 30
    calls = []

    def dry_run(request):
        calls.append(request)
        return ToolResult(
            tool_id=request.tool_id,
            target=request.target,
            summary="Mock dry run",
        )

    monkeypatch.setattr(plan_api, "execute_tool", dry_run)
    plan_response = client.post(
        "/api/plans",
        json={"request": "Install Google Chrome", "language": "en"},
    )
    assert plan_response.status_code == 200
    plan_id = plan_response.json()["dry_run_plan"]["plan_id"]

    missing_step_up = client.post(f"/api/plans/{plan_id}/approve", json={})
    assert missing_step_up.status_code == 403
    assert calls == []

    challenge = client.post(f"/api/plans/{plan_id}/step-up", json={})
    assert challenge.status_code == 200
    challenge_id = challenge.json()["challenge_id"]

    approved = client.post(
        f"/api/plans/{plan_id}/approve",
        json={
            "challenge_id": challenge_id,
            "totp_code": code_at(RFC_SECRET, now[0]),
        },
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert approved.json()["notice"] == "DRY_RUN_ONLY_NO_CHANGES_MADE"
    assert len(calls) == 1

    # A consumed challenge cannot be replayed to retrieve a cached result.
    replayed = client.post(
        f"/api/plans/{plan_id}/approve",
        json={
            "challenge_id": challenge_id,
            "totp_code": code_at(RFC_SECRET, now[0]),
        },
    )
    assert replayed.status_code == 403
    assert len(calls) == 1

    # Idempotent retry is permitted only after a fresh TOTP step and challenge.
    now[0] += 30
    retry_challenge = client.post(f"/api/plans/{plan_id}/step-up", json={})
    assert retry_challenge.status_code == 200
    repeated = client.post(
        f"/api/plans/{plan_id}/approve",
        json={
            "challenge_id": retry_challenge.json()["challenge_id"],
            "totp_code": code_at(RFC_SECRET, now[0]),
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["tool_result"] == approved.json()["tool_result"]
    assert len(calls) == 1

    # Cached results remain protected by the authenticated route dependency.
    client.cookies.clear()
    unauthenticated = client.post(
        f"/api/plans/{plan_id}/approve",
        json={
            "challenge_id": retry_challenge.json()["challenge_id"],
            "totp_code": "000000",
        },
    )
    assert unauthenticated.status_code == 401
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/plans", {"request": "Install Google Chrome", "language": "en"}),
        ("/api/software/discovery/search", {"query": "Google Chrome"}),
    ],
)
def test_protected_routers_fail_closed_when_authentication_is_disabled(
    tmp_path, path, payload
):
    from agent_backend.main import create_app

    client = TestClient(
        create_app(load_settings(load_env_file=False)),
        base_url="http://127.0.0.1:8000",
        headers=HEADERS,
    )

    response = client.post(path, json=payload)

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is not configured."}


@pytest.mark.parametrize(
    ("environ", "argv"),
    [
        ({"WEB_CONCURRENCY": "2"}, []),
        ({}, ["--workers", "2"]),
        ({"GUNICORN_CMD_ARGS": "--workers=3"}, []),
        ({"UVICORN_WORKERS": "not-a-number"}, []),
    ],
)
def test_multi_worker_configuration_is_rejected(environ, argv):
    from agent_backend.main import enforce_single_worker

    with pytest.raises(RuntimeError):
        enforce_single_worker(environ=environ, argv=argv)


def test_single_worker_configuration_is_accepted():
    from agent_backend.main import enforce_single_worker

    enforce_single_worker(environ={"WEB_CONCURRENCY": "1"}, argv=[])



def test_build_auth_services_keeps_google_dashboard_available_when_secret_load_fails(
    monkeypatch
):
    from agent_backend.auth_api import build_auth_services
    from agent_backend.authenticator import SecretStoreError

    settings = replace(
        load_settings(load_env_file=False),
        google_oidc_client_id="test-client-id",
        google_oidc_client_secret="test-client-secret",
        google_oidc_redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        master_google_sub=OWNER,
        app_session_ttl_seconds=1800,
        authenticator_secret_path=(
            Path(__file__).resolve().parents[2]
            / ".agent-state" / "authenticator" / "authenticator.json"
        ),
    )

    def unavailable(self, *, owner_sub):
        raise SecretStoreError("simulated unreadable storage")

    monkeypatch.setattr(EncryptedTotpSecretFileStore, "load", unavailable)
    services = build_auth_services(settings)
    assert services is not None

    from agent_backend.main import create_app

    client = TestClient(
        create_app(settings, auth_services=services),
        base_url="http://127.0.0.1:8000",
        headers=HEADERS,
    )
    sign_in(client, services)
    session = client.get("/api/auth/session")
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
    assert session.json()["authenticator_storage_available"] is False
    assert client.get("/api/auth/google/start").status_code == 200


def test_authenticator_change_reports_persisted_success_when_session_rotation_fails(
    tmp_path, monkeypatch
):
    from agent_backend.auth_audit import AUTH_AUDIT_SINK

    AUTH_AUDIT_SINK.clear()
    client, services, now = build_client(tmp_path)
    sign_in(client, services, recently_authenticated=True)
    enrollment = client.post("/api/authenticator/enrollment", json={})
    assert enrollment.status_code == 200
    monkeypatch.setattr(services.sessions, "rotate", lambda token: None)

    response = client.post(
        "/api/authenticator/enrollment/confirm",
        json={
            "enrollment_id": enrollment.json()["enrollment_id"],
            "code": code_at(RFC_SECRET, now[0]),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"enrolled": True}
    assert services.secret_store.load(owner_sub=OWNER) == RFC_SECRET
    assert any(
        event.event_type == "auth.enrollment" and event.outcome == "success"
        for event in AUTH_AUDIT_SINK.snapshot()
    )



def test_build_auth_services_does_not_block_first_enrollment_when_secret_is_absent(monkeypatch):
    from agent_backend.auth_api import build_auth_services

    monkeypatch.setattr(
        EncryptedTotpSecretFileStore,
        "load",
        lambda self, *, owner_sub: None,
    )

    settings = replace(
        load_settings(load_env_file=False),
        google_oidc_client_id="test-client-id",
        google_oidc_client_secret="test-client-secret",
        google_oidc_redirect_uri="http://127.0.0.1:8000/auth/google/callback",
        master_google_sub=OWNER,
        app_session_ttl_seconds=1800,
        authenticator_secret_path=(
            Path(__file__).resolve().parents[2]
            / ".agent-state" / "authenticator" / "authenticator.json"
        ),
    )

    services = build_auth_services(settings)

    assert services is not None
    assert services.enrollment._replay_guard._last_consumed.get(OWNER) is None
