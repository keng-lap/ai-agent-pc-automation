from dataclasses import replace

from fastapi.testclient import TestClient

from agent_backend.auth_api import (
    AuthServices,
    SESSION_COOKIE_NAME,
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

    def begin_login(self):
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
        authenticator_secret_path=tmp_path / "authenticator.json",
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


def sign_in(client, services):
    identity = GoogleIdentity(sub=OWNER, email="owner@example.test")
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
    }


def test_google_callback_creates_http_only_master_session(tmp_path):
    client, services, _now = build_client(tmp_path)

    response = client.get(
        "/auth/google/callback?state=valid-state&code=valid-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
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
    assert response.json() == {
        "authorization_url": "https://accounts.google.com/test-login"
    }


def test_api_routes_require_master_session_when_auth_is_enabled(tmp_path):
    client, _services, _now = build_client(tmp_path)

    response = client.post(
        "/api/plans",
        json={"request": "Install Google Chrome", "language": "en"},
    )

    assert response.status_code == 401


def test_authenticator_enrollment_and_confirmation_are_one_time(tmp_path):
    client, _services, now = build_client(tmp_path)
    sign_in(client, _services)

    start = client.post("/api/authenticator/enrollment", json={})
    assert start.status_code == 200
    assert start.json()["qr_data_uri"].startswith("data:image/svg+xml;base64,")

    confirmed = client.post(
        "/api/authenticator/enrollment/confirm",
        json={
            "enrollment_id": start.json()["enrollment_id"],
            "code": code_at(RFC_SECRET, now[0]),
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {"enrolled": True}
    assert client.get("/api/authenticator/status").json()["authenticator_enrolled"] is True

    second = client.post("/api/authenticator/enrollment", json={})
    assert second.status_code == 409


def test_plan_approval_requires_fresh_totp_bound_to_exact_plan(tmp_path, monkeypatch):
    from agent_backend import plan_api
    from agent_backend.tools import ToolResult

    client, services, now = build_client(tmp_path)
    sign_in(client, services)
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

    # Cached dry-run result is idempotent and does not dispatch again.
    repeated = client.post(
        f"/api/plans/{plan_id}/approve",
        json={"challenge_id": challenge_id, "totp_code": "000000"},
    )
    assert repeated.status_code == 200
    assert len(calls) == 1
