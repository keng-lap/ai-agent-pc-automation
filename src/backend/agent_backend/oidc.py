"""Google OpenID Connect authorization-code/PKCE adapter for F-516-01.

This module verifies identity only. It never retains Google access/refresh tokens,
requests provider APIs beyond OIDC, or forwards prompts, plans, files or PC data.
The caller must separately enforce the single-Master-User allowlist and create
an application session after this module returns a verified identity.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
OIDC_SCOPES = "openid email profile"
OIDC_TRANSACTION_TTL_SECONDS = 300
MAX_PENDING_OIDC_TRANSACTIONS = 64
MAX_ID_TOKEN_AGE_SECONDS = 600
CLOCK_FUTURE_TOLERANCE_SECONDS = 60


class OidcAuthenticationError(RuntimeError):
    """Raised when an OIDC callback cannot be verified safely."""


@dataclass(frozen=True, slots=True)
class OidcTransaction:
    """Short-lived server-side OIDC state, nonce and PKCE verifier."""

    state: str
    nonce: str
    code_verifier: str
    created_at: float
    expires_at: float


@dataclass(frozen=True, slots=True)
class LoginStart:
    """Only the authorization URL is returned to the browser."""

    authorization_url: str


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    """Verified Google identity; the stable subject is the owner key."""

    sub: str
    email: str


class OidcTransactionStore:
    """Bounded, one-time, process-local storage for OIDC anti-CSRF state."""

    def __init__(self, *, clock=None, ttl_seconds: int = OIDC_TRANSACTION_TTL_SECONDS):
        if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 600:
            raise ValueError("OIDC transaction TTL must be between 60 and 600 seconds")
        self._clock = clock or time.time
        self._ttl_seconds = ttl_seconds
        self._transactions: dict[str, OidcTransaction] = {}
        self._lock = threading.RLock()

    def create(self) -> OidcTransaction:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            raise OidcAuthenticationError("OIDC clock is invalid.")
        with self._lock:
            self._remove_expired(float(now))
            if len(self._transactions) >= MAX_PENDING_OIDC_TRANSACTIONS:
                raise OidcAuthenticationError("Too many pending sign-in attempts.")
            verifier = secrets.token_urlsafe(48)
            transaction = OidcTransaction(
                state=secrets.token_urlsafe(32),
                nonce=secrets.token_urlsafe(32),
                code_verifier=verifier,
                created_at=float(now),
                expires_at=float(now) + self._ttl_seconds,
            )
            self._transactions[transaction.state] = transaction
            return transaction

    def consume(self, state: str) -> OidcTransaction | None:
        if not isinstance(state, str) or not 16 <= len(state) <= 256:
            return None
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            return None
        with self._lock:
            transaction = self._transactions.pop(state, None)
            if transaction is None or float(now) >= transaction.expires_at:
                return None
            return transaction

    def _remove_expired(self, now: float) -> None:
        expired = [
            state
            for state, transaction in self._transactions.items()
            if now >= transaction.expires_at
        ]
        for state in expired:
            self._transactions.pop(state, None)


class MasterUserAllowlist:
    """Exact stable-sub allowlist for the one Master User; never auto-enrolls."""

    def __init__(self, master_google_sub: str) -> None:
        if (
            not isinstance(master_google_sub, str)
            or not 1 <= len(master_google_sub) <= 256
        ):
            raise ValueError("A pre-provisioned Master User Google subject is required.")
        self._master_sub = master_google_sub

    def is_master_user(self, identity: GoogleIdentity) -> bool:
        return (
            isinstance(identity, GoogleIdentity)
            and hmac.compare_digest(identity.sub, self._master_sub)
        )

    def require_master_user(self, identity: GoogleIdentity) -> None:
        if not self.is_master_user(identity):
            raise OidcAuthenticationError("Google identity is not the enrolled Master User.")


class GoogleOidcClient:
    """Google OIDC client with Authorization Code + PKCE and strict ID-token checks."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transaction_store: OidcTransactionStore | None = None,
        http_session=None,
        token_verifier: Callable[[str], Mapping[str, object]] | None = None,
        clock=None,
    ) -> None:
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 512:
            raise ValueError("Google OIDC client ID is required.")
        if not isinstance(client_secret, str) or not 1 <= len(client_secret) <= 512:
            raise ValueError("Google OIDC client secret is required.")
        parsed_redirect = urlparse(redirect_uri) if isinstance(redirect_uri, str) else None
        if (
            parsed_redirect is None
            or parsed_redirect.scheme != "http"
            or parsed_redirect.hostname not in {"127.0.0.1", "localhost"}
            or parsed_redirect.port is None
            or parsed_redirect.username is not None
            or parsed_redirect.password is not None
            or parsed_redirect.fragment
        ):
            raise ValueError("Google OIDC redirect URI must use a loopback HTTP address.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._transactions = transaction_store or OidcTransactionStore()
        self._http = http_session or requests.Session()
        self._token_verifier = token_verifier or self._verify_google_signature
        self._clock = clock or time.time

    def begin_login(self) -> LoginStart:
        transaction = self._transactions.create()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(transaction.code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": OIDC_SCOPES,
            "state": transaction.state,
            "nonce": transaction.nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return LoginStart(
            authorization_url=f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"
        )

    def complete_login(self, *, state: str, code: str) -> GoogleIdentity:
        transaction = self._transactions.consume(state)
        if transaction is None:
            raise OidcAuthenticationError("OIDC state is invalid, expired or already used.")
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise OidcAuthenticationError("Google authorization code is invalid.")

        try:
            response = self._http.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": transaction.code_verifier,
                },
                timeout=5,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise OidcAuthenticationError("Google token exchange failed.")
            payload = response.json()
        except OidcAuthenticationError:
            raise
        except Exception:
            raise OidcAuthenticationError("Google token exchange failed.") from None

        if not isinstance(payload, dict) or not isinstance(payload.get("id_token"), str):
            raise OidcAuthenticationError("Google ID token is missing.")
        scope = payload.get("scope")
        if scope is not None and (
            not isinstance(scope, str) or "openid" not in scope.split()
        ):
            raise OidcAuthenticationError("Google response did not grant OIDC scope.")

        # Access and refresh tokens are intentionally discarded and never retained.
        return self._validate_identity_token(
            payload["id_token"],
            expected_nonce=transaction.nonce,
        )

    def _verify_google_signature(self, token: str) -> Mapping[str, object]:
        try:
            return id_token.verify_oauth2_token(
                token,
                GoogleRequest(),
                audience=self._client_id,
            )
        except Exception:
            raise OidcAuthenticationError("Google ID token signature is invalid.") from None

    def _validate_identity_token(
        self,
        token: str,
        *,
        expected_nonce: str,
    ) -> GoogleIdentity:
        try:
            claims = self._token_verifier(token)
        except OidcAuthenticationError:
            raise
        except Exception:
            raise OidcAuthenticationError("Google ID token is invalid.") from None
        if not isinstance(claims, Mapping):
            raise OidcAuthenticationError("Google ID token claims are invalid.")

        issuer = claims.get("iss")
        audience = claims.get("aud")
        nonce = claims.get("nonce")
        subject = claims.get("sub")
        email = claims.get("email")
        email_verified = claims.get("email_verified")
        authorized_party = claims.get("azp")
        expires_at = claims.get("exp")
        issued_at = claims.get("iat")
        now = self._clock()

        valid_audience = (
            audience == self._client_id
            or (
                isinstance(audience, list)
                and self._client_id in audience
                and len(audience) == 1
            )
        )
        valid_time = (
            not isinstance(now, bool)
            and isinstance(now, (int, float))
            and math.isfinite(now)
            and isinstance(expires_at, (int, float))
            and not isinstance(expires_at, bool)
            and math.isfinite(expires_at)
            and isinstance(issued_at, (int, float))
            and not isinstance(issued_at, bool)
            and math.isfinite(issued_at)
            and now < expires_at
            and issued_at <= now + CLOCK_FUTURE_TOLERANCE_SECONDS
            and now - issued_at <= MAX_ID_TOKEN_AGE_SECONDS
        )
        if (
            issuer not in GOOGLE_ISSUERS
            or not valid_audience
            or (authorized_party is not None and authorized_party != self._client_id)
            or not isinstance(nonce, str)
            or not hmac.compare_digest(nonce, expected_nonce)
            or not isinstance(subject, str)
            or not 1 <= len(subject) <= 256
            or not isinstance(email, str)
            or not 3 <= len(email) <= 254
            or email_verified is not True
            or not valid_time
        ):
            raise OidcAuthenticationError("Google identity claims failed validation.")
        return GoogleIdentity(sub=subject, email=email)
