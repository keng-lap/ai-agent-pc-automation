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
    MAX_RECENT_AUTH_AGE_SECONDS,
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

    secret_store = EncryptedTotpSecretFileStore(
        settings.authenticator_secret_path,
        WindowsDpapiProtector(),
    )
    replay_guard = TotpReplayGuard()
    if secret_store.load(owner_sub=settings.master_google_sub) is not None:
        replay_guard.block_through_current_step(owner_key=settings.master_google_sub)
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


def require_session(request: Request) -> SessionPrincipal:
    """Fail closed unless an enrolled Master User session is available."""
    services: AuthServices | None = getattr(request.app.state, "auth_services", None)
    if services is None:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
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


def _frontend_redirect(request: Request, status: str) -> RedirectResponse:
    settings: Settings = request.app.state.settings
    response = RedirectResponse(
        f"http://127.0.0.1:{settings.frontend_port}/?login={status}",
        status_code=303,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


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
def start_google_login(
    request: Request,
    response: Response,
) -> GoogleLoginStartResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    services = _services(request)
    try:
        result = services.oidc.begin_login()
    except OidcAuthenticationError:
        raise HTTPException(status_code=429, detail="Sign-in temporarily unavailable.") from None
    return GoogleLoginStartResponse(authorization_url=result.authorization_url)


@router.get("/api/auth/google/reauth/start", response_model=GoogleLoginStartResponse)
def start_google_reauthentication(
    request: Request,
    response: Response,
) -> GoogleLoginStartResponse:
    """Start a fresh Google authentication ceremony for sensitive account changes."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        result = services.oidc.begin_login(require_recent_auth=True)
    except OidcAuthenticationError:
        raise HTTPException(status_code=429, detail="Re-authentication temporarily unavailable.") from None
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
        return _frontend_redirect(request, "unavailable")
    if error is not None or state is None or code is None:
        record_auth_audit_event(
            event_type="auth.sign_in",
            outcome="denied",
            reason="identity_invalid",
        )
        return _frontend_redirect(request, "failed")

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
        return _frontend_redirect(request, "failed")

    record_auth_audit_event(event_type="auth.sign_in", outcome="success")
    settings: Settings = request.app.state.settings
    response = _frontend_redirect(request, "success")
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
def begin_authenticator_enrollment(
    request: Request,
    response: Response,
) -> EnrollmentStartResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not services.sessions.consume_recent_auth(
        principal, max_age_seconds=MAX_RECENT_AUTH_AGE_SECONDS
    ):
        record_auth_audit_event(
            event_type="auth.enrollment",
            outcome="denied",
            reason="reauthentication_required",
        )
        raise HTTPException(status_code=403, detail="Fresh Google sign-in required.")
    try:
        start = services.enrollment.begin(
            owner_sub=principal.owner_sub,
            account_name="Master User",
        )
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=409, detail="Authenticator enrollment is unavailable.") from None
    return EnrollmentStartResponse(
        enrollment_id=start.enrollment_id,
        qr_data_uri=start.qr_data_uri,
        expires_at=start.expires_at,
    )


def _complete_authenticator_setup(
    payload: EnrollmentConfirmRequest,
    request: Request,
    response: Response,
    *,
    event_type: str,
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
            event_type=event_type,
            outcome="denied",
            reason="invalid_totp",
        )
        raise HTTPException(status_code=400, detail="Authenticator confirmation failed.")
    token = request.cookies.get(SESSION_COOKIE_NAME)
    rotated = services.sessions.rotate(token or "")
    if rotated is None:
        raise HTTPException(status_code=401, detail="Authentication session expired.")
    settings: Settings = request.app.state.settings
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=rotated.token,
        max_age=settings.app_session_ttl_seconds,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    record_auth_audit_event(event_type=event_type, outcome="success")
    return {"enrolled": True}


@router.post("/api/authenticator/enrollment/confirm")
def confirm_authenticator_enrollment(
    payload: EnrollmentConfirmRequest,
    request: Request,
    response: Response,
) -> dict[str, bool]:
    return _complete_authenticator_setup(
        payload,
        request,
        response,
        event_type="auth.enrollment",
    )


@router.post("/api/authenticator/recovery", response_model=EnrollmentStartResponse)
def begin_authenticator_recovery(
    request: Request,
    response: Response,
) -> EnrollmentStartResponse:
    """Start replacement using fresh Google identity proof, never the lost TOTP."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    services = _services(request)
    principal = require_session(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not services.sessions.consume_recent_auth(
        principal, max_age_seconds=MAX_RECENT_AUTH_AGE_SECONDS
    ):
        record_auth_audit_event(
            event_type="auth.recovery",
            outcome="denied",
            reason="reauthentication_required",
        )
        raise HTTPException(status_code=403, detail="Fresh Google sign-in required.")
    try:
        start = services.enrollment.begin_recovery(
            owner_sub=principal.owner_sub,
            account_name="Master User",
        )
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=409, detail="Authenticator recovery is unavailable.") from None
    return EnrollmentStartResponse(
        enrollment_id=start.enrollment_id,
        qr_data_uri=start.qr_data_uri,
        expires_at=start.expires_at,
    )


@router.post("/api/authenticator/recovery/confirm")
def confirm_authenticator_recovery(
    payload: EnrollmentConfirmRequest,
    request: Request,
    response: Response,
) -> dict[str, bool]:
    return _complete_authenticator_setup(
        payload,
        request,
        response,
        event_type="auth.recovery",
    )
