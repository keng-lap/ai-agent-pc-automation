"""Google login, Master User session, and authenticator enrollment API."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .auth_audit import record_auth_audit_event
from .authenticator import (
    AuthenticatorEnrollmentManager,
    EncryptedTotpSecretFileStore,
    SecretStoreError,
    WindowsDpapiProtector,
)
from .config import Settings
from .oidc import (
    ApplicationSessionStore,
    GoogleOidcClient,
    MasterUserAllowlist,
    OidcAuthenticationError,
    OidcTransactionStore,
    SessionPrincipal,
)
from .step_up import StepUpChallengeStore
from .totp import TotpReplayGuard

SESSION_COOKIE_NAME = "agent_session"
router = APIRouter()


@dataclass(slots=True)
class AuthServices:
    oidc: GoogleOidcClient
    allowlist: MasterUserAllowlist
    sessions: ApplicationSessionStore
    secret_store: EncryptedTotpSecretFileStore
    enrollment: AuthenticatorEnrollmentManager
    step_up: StepUpChallengeStore


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool
    authenticated: bool
    authenticator_enrolled: bool = False


class GoogleLoginStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    authorization_url: str


class EnrollmentStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enrollment_id: str
    qr_data_uri: str
    expires_at: float


class EnrollmentConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enrollment_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


def build_auth_services(settings: Settings) -> AuthServices | None:
    """Create real local auth services only when every required setting is present."""
    if not settings.auth_enabled:
        return None
    if (
        settings.google_oidc_client_id is None
        or settings.google_oidc_client_secret is None
        or settings.google_oidc_redirect_uri is None
        or settings.master_google_sub is None
        or settings.app_session_ttl_seconds is None
        or settings.authenticator_secret_path is None
    ):
        raise RuntimeError("Google authentication settings are incomplete.")

    replay_guard = TotpReplayGuard()
    secret_store = EncryptedTotpSecretFileStore(
        settings.authenticator_secret_path,
        WindowsDpapiProtector(),
    )
    return AuthServices(
        oidc=GoogleOidcClient(
            client_id=settings.google_oidc_client_id,
            client_secret=settings.google_oidc_client_secret,
            redirect_uri=settings.google_oidc_redirect_uri,
            transaction_store=OidcTransactionStore(),
        ),
        allowlist=MasterUserAllowlist(settings.master_google_sub),
        sessions=ApplicationSessionStore(
            ttl_seconds=settings.app_session_ttl_seconds,
        ),
        secret_store=secret_store,
        enrollment=AuthenticatorEnrollmentManager(
            secret_store=secret_store,
            replay_guard=replay_guard,
        ),
        step_up=StepUpChallengeStore(replay_guard=replay_guard),
    )


def require_session(request: Request) -> SessionPrincipal | None:
    """Require the enrolled Master User session when authentication is enabled."""
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    if services is None:
        return None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    principal = services.sessions.resolve(token or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    request.state.principal = principal
    return principal


def _services(request: Request) -> AuthServices:
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Google authentication is not configured.")
    return services


def _frontend_url(request: Request, status: str) -> str:
    settings: Settings = request.app.state.settings
    return f"http://127.0.0.1:{settings.frontend_port}/?login={status}"


@router.get("/api/auth/session", response_model=AuthSessionResponse)
def get_auth_session(request: Request) -> AuthSessionResponse:
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    if services is None:
        return AuthSessionResponse(enabled=False, authenticated=False)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    principal = services.sessions.resolve(token or "")
    if principal is None:
        return AuthSessionResponse(enabled=True, authenticated=False)
    try:
        enrolled = services.secret_store.load(owner_sub=principal.owner_sub) is not None
    except SecretStoreError:
        raise HTTPException(status_code=503, detail="Authenticator storage unavailable.") from None
    return AuthSessionResponse(
        enabled=True,
        authenticated=True,
        authenticator_enrolled=enrolled,
    )


@router.get("/api/auth/google/start", response_model=GoogleLoginStartResponse)
def start_google_login(request: Request) -> GoogleLoginStartResponse:
    services = _services(request)
    try:
        result = services.oidc.begin_login()
    except OidcAuthenticationError:
        raise HTTPException(status_code=429, detail="Sign-in temporarily unavailable.") from None
    return GoogleLoginStartResponse(authorization_url=result.authorization_url)


@router.get("/auth/google/callback")
def complete_google_login(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> Response:
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    if services is None:
        return RedirectResponse(_frontend_url(request, "unavailable"), status_code=303)
    if error is not None or state is None or code is None:
        record_auth_audit_event(
            event_type="auth.sign_in",
            outcome="denied",
            reason="identity_invalid",
        )
        return RedirectResponse(_frontend_url(request, "failed"), status_code=303)

    try:
        identity = services.oidc.complete_login(state=state, code=code)
        services.allowlist.require_master_user(identity)
        credential = services.sessions.create(
            identity=identity,
            allowlist=services.allowlist,
        )
    except OidcAuthenticationError as exc:
        reason = (
            "owner_not_allowlisted"
            if "not the enrolled Master User" in str(exc)
            else "identity_invalid"
        )
        record_auth_audit_event(
            event_type="auth.sign_in",
            outcome="denied",
            reason=reason,
        )
        return RedirectResponse(_frontend_url(request, "failed"), status_code=303)

    record_auth_audit_event(event_type="auth.sign_in", outcome="success")
    settings: Settings = request.app.state.settings
    response = RedirectResponse(_frontend_url(request, "success"), status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=credential.token,
        max_age=settings.app_session_ttl_seconds,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/api/auth/logout")
def logout(request: Request) -> Response:
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    response = Response(content='{"logged_out":true}', media_type="application/json")
    if services is not None:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            services.sessions.revoke(token)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return response


@router.get("/api/authenticator/status", response_model=AuthSessionResponse)
def authenticator_status(request: Request) -> AuthSessionResponse:
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        enrolled = services.secret_store.load(owner_sub=principal.owner_sub) is not None
    except SecretStoreError:
        raise HTTPException(status_code=503, detail="Authenticator storage unavailable.") from None
    return AuthSessionResponse(
        enabled=True,
        authenticated=True,
        authenticator_enrolled=enrolled,
    )


@router.post("/api/authenticator/enrollment", response_model=EnrollmentStartResponse)
def begin_authenticator_enrollment(request: Request) -> EnrollmentStartResponse:
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        start = services.enrollment.begin(
            owner_sub=principal.owner_sub,
            account_name="Master User",
        )
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=409, detail="Authenticator enrollment is unavailable.") from None
    record_auth_audit_event(event_type="auth.enrollment", outcome="success")
    return EnrollmentStartResponse(
        enrollment_id=start.enrollment_id,
        qr_data_uri=start.qr_data_uri,
        expires_at=start.expires_at,
    )


@router.post("/api/authenticator/enrollment/confirm")
def confirm_authenticator_enrollment(
    payload: EnrollmentConfirmRequest,
    request: Request,
) -> dict[str, bool]:
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    confirmed = services.enrollment.confirm(
        enrollment_id=payload.enrollment_id,
        owner_sub=principal.owner_sub,
        code=payload.code,
    )
    if not confirmed:
        record_auth_audit_event(
            event_type="auth.enrollment",
            outcome="denied",
            reason="invalid_totp",
        )
        raise HTTPException(status_code=400, detail="Authenticator confirmation failed.")
    record_auth_audit_event(event_type="auth.enrollment", outcome="success")
    return {"enrolled": True}
