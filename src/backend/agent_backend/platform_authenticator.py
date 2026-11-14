"""Local platform-authenticator ceremonies for TOTP setup and recovery.

Google OIDC remains the application login. This module provides WebAuthn
registration/assertion as an additional local user-verification gate only.
Challenges are process-local, short-lived, one-use, and bound to owner/session.
Credential private keys never leave the platform authenticator.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

CHALLENGE_TTL_SECONDS = 120
MAX_PENDING_CHALLENGES = 16
MAX_CREDENTIAL_RESPONSE_BYTES = 32_768


class PlatformAuthenticatorError(RuntimeError):
    """Raised when a platform-authenticator ceremony cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class PlatformCredential:
    owner_sub: str
    credential_id: bytes
    public_key: bytes
    sign_count: int


@dataclass(frozen=True, slots=True)
class _PendingChallenge:
    challenge: bytes
    owner_sub: str
    session_id: str
    purpose: str
    expires_at: float


class PlatformCredentialStore:
    """Single-owner encrypted credential metadata store."""

    def __init__(self, path: str | Path, protector: Any) -> None:
        self._path = Path(path)
        self._protector = protector
        self._lock = threading.RLock()

    def load(self, *, owner_sub: str) -> PlatformCredential | None:
        with self._lock:
            raw = self._read()
            if raw is None:
                return None
            try:
                payload = json.loads(self._protector.unprotect(raw).decode("utf-8"))
                if not isinstance(payload, dict) or set(payload) != {
                    "owner_sub", "credential_id", "public_key", "sign_count"
                }:
                    raise ValueError
                if payload["owner_sub"] != owner_sub:
                    return None
                credential_id = base64.b64decode(payload["credential_id"], validate=True)
                public_key = base64.b64decode(payload["public_key"], validate=True)
                sign_count = payload["sign_count"]
                if (
                    not credential_id or len(credential_id) > 1024
                    or not public_key or len(public_key) > 4096
                    or type(sign_count) is not int or sign_count < 0
                ):
                    raise ValueError
                return PlatformCredential(owner_sub, credential_id, public_key, sign_count)
            except Exception:
                raise PlatformAuthenticatorError("Platform credential storage is invalid.") from None

    def save_new(self, credential: PlatformCredential) -> None:
        protected = self._encode(credential)
        with self._lock:
            if self._read() is not None:
                raise PlatformAuthenticatorError("A platform credential is already registered.")
            self._write_new(protected)

    def update_counter(self, credential: PlatformCredential, new_sign_count: int) -> None:
        if type(new_sign_count) is not int or new_sign_count < 0:
            raise PlatformAuthenticatorError("Platform credential counter is invalid.")
        updated = PlatformCredential(
            credential.owner_sub, credential.credential_id,
            credential.public_key, new_sign_count,
        )
        with self._lock:
            current = self.load(owner_sub=credential.owner_sub)
            if current != credential:
                raise PlatformAuthenticatorError("Platform credential changed during verification.")
            self._replace(self._encode(updated))

    def _encode(self, credential: PlatformCredential) -> bytes:
        if (
            not isinstance(credential.owner_sub, str)
            or not 1 <= len(credential.owner_sub) <= 256
        ):
            raise PlatformAuthenticatorError("Platform credential owner is invalid.")
        payload = json.dumps({
            "owner_sub": credential.owner_sub,
            "credential_id": base64.b64encode(credential.credential_id).decode("ascii"),
            "public_key": base64.b64encode(credential.public_key).decode("ascii"),
            "sign_count": credential.sign_count,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        protected = self._protector.protect(payload)
        if not isinstance(protected, bytes) or not protected:
            raise PlatformAuthenticatorError("Platform credential protection failed.")
        return protected

    def _read(self) -> bytes | None:
        if os.name == "nt":
            try:
                from .windows_secret_storage import WindowsSecretFile
                return WindowsSecretFile(self._path).read()
            except FileNotFoundError:
                return None
            except Exception:
                raise PlatformAuthenticatorError("Platform credential storage is unavailable.") from None
        if self._path.is_symlink():
            raise PlatformAuthenticatorError("Platform credential path is not trusted.")
        if not self._path.exists():
            return None
        try:
            return self._path.read_bytes()
        except OSError:
            raise PlatformAuthenticatorError("Platform credential storage is unavailable.") from None

    def _write_new(self, protected: bytes) -> None:
        if os.name == "nt":
            try:
                from .windows_secret_storage import WindowsSecretFile
                WindowsSecretFile(self._path).create_exclusive(protected)
                return
            except Exception:
                raise PlatformAuthenticatorError("Platform credential storage failed.") from None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            raise PlatformAuthenticatorError("Platform credential storage failed.") from None

    def _replace(self, protected: bytes) -> None:
        if os.name == "nt":
            try:
                from .windows_secret_storage import WindowsSecretFile
                WindowsSecretFile(self._path).replace(protected)
                return
            except Exception:
                raise PlatformAuthenticatorError("Platform credential counter update failed.") from None
        if self._path.is_symlink() or not self._path.is_file():
            raise PlatformAuthenticatorError("Platform credential path is not trusted.")
        temporary = self._path.with_name(f".{self._path.name}.{secrets.token_hex(12)}.tmp")
        try:
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise PlatformAuthenticatorError("Platform credential counter update failed.") from None


class PlatformAuthenticatorManager:
    """One-credential WebAuthn manager for local TOTP setup/recovery proof."""

    def __init__(
        self,
        *,
        credential_store: PlatformCredentialStore,
        rp_id: str = "localhost",
        expected_origin: str = "http://localhost:4200",
        clock=None,
    ) -> None:
        if rp_id != "localhost" or expected_origin != "http://localhost:4200":
            raise ValueError("Only the configured localhost WebAuthn origin is supported.")
        self._store = credential_store
        self._rp_id = rp_id
        self._origin = expected_origin
        self._clock = clock or time.monotonic
        self._pending: dict[str, _PendingChallenge] = {}
        self._lock = threading.RLock()

    def begin_registration(self, *, owner_sub: str, session_id: str) -> dict[str, Any]:
        if self._store.load(owner_sub=owner_sub) is not None:
            raise PlatformAuthenticatorError("A platform credential is already registered.")
        ceremony_id, pending = self._new_challenge(owner_sub, session_id, "registration")
        options = generate_registration_options(
            rp_id=self._rp_id,
            rp_name="AI Agent PC Automation",
            user_name="Master User",
            user_display_name="Master User",
            user_id=hashlib.sha256(owner_sub.encode("utf-8")).digest()[:32],
            challenge=pending.challenge,
            timeout=CHALLENGE_TTL_SECONDS * 1000,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        return {"ceremony_id": ceremony_id, "public_key": json.loads(options_to_json(options))}

    def complete_registration(
        self, *, ceremony_id: str, owner_sub: str, session_id: str,
        credential: dict[str, Any],
    ) -> None:
        pending = self._consume(ceremony_id, owner_sub, session_id, "registration")
        self._validate_response_size(credential)
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=pending.challenge,
                expected_rp_id=self._rp_id,
                expected_origin=self._origin,
                require_user_verification=True,
            )
            if credential.get("authenticatorAttachment") != "platform":
                raise PlatformAuthenticatorError("A platform authenticator is required.")
            self._store.save_new(PlatformCredential(
                owner_sub=owner_sub,
                credential_id=verified.credential_id,
                public_key=verified.credential_public_key,
                sign_count=verified.sign_count,
            ))
        except PlatformAuthenticatorError:
            raise
        except Exception:
            raise PlatformAuthenticatorError("Platform credential registration failed.") from None

    def begin_assertion(
        self, *, owner_sub: str, session_id: str, purpose: str
    ) -> dict[str, Any]:
        if purpose not in {"enrollment", "recovery"}:
            raise PlatformAuthenticatorError("Platform authenticator purpose is invalid.")
        credential = self._store.load(owner_sub=owner_sub)
        if credential is None:
            raise PlatformAuthenticatorError("No trusted platform credential is registered.")
        ceremony_id, pending = self._new_challenge(owner_sub, session_id, purpose)
        options = generate_authentication_options(
            rp_id=self._rp_id,
            challenge=pending.challenge,
            timeout=CHALLENGE_TTL_SECONDS * 1000,
            allow_credentials=[PublicKeyCredentialDescriptor(id=credential.credential_id)],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return {"ceremony_id": ceremony_id, "public_key": json.loads(options_to_json(options))}

    def complete_assertion(
        self, *, ceremony_id: str, owner_sub: str, session_id: str,
        purpose: str, credential_response: dict[str, Any],
    ) -> None:
        pending = self._consume(ceremony_id, owner_sub, session_id, purpose)
        self._validate_response_size(credential_response)
        credential = self._store.load(owner_sub=owner_sub)
        if credential is None:
            raise PlatformAuthenticatorError("No trusted platform credential is registered.")
        try:
            expected_id = base64.urlsafe_b64encode(credential.credential_id).rstrip(b"=").decode("ascii")
            if credential_response.get("id") != expected_id:
                raise PlatformAuthenticatorError("Platform credential does not belong to this owner.")
            verified = verify_authentication_response(
                credential=credential_response,
                expected_challenge=pending.challenge,
                expected_rp_id=self._rp_id,
                expected_origin=self._origin,
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
                require_user_verification=True,
            )
            if not verified.user_verified:
                raise PlatformAuthenticatorError("Platform user verification is required.")
            self._store.update_counter(credential, verified.new_sign_count)
        except PlatformAuthenticatorError:
            raise
        except Exception:
            raise PlatformAuthenticatorError("Platform authenticator verification failed.") from None

    def _new_challenge(
        self, owner_sub: str, session_id: str, purpose: str
    ) -> tuple[str, _PendingChallenge]:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            raise PlatformAuthenticatorError("Authenticated owner is invalid.")
        if not isinstance(session_id, str) or not 16 <= len(session_id) <= 256:
            raise PlatformAuthenticatorError("Authenticated session is invalid.")
        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise PlatformAuthenticatorError("Challenge clock is invalid.")
        with self._lock:
            self._remove_expired(float(now))
            if len(self._pending) >= MAX_PENDING_CHALLENGES:
                raise PlatformAuthenticatorError("Too many pending platform-authenticator ceremonies.")
            ceremony_id = secrets.token_hex(16)
            pending = _PendingChallenge(
                challenge=secrets.token_bytes(32),
                owner_sub=owner_sub,
                session_id=session_id,
                purpose=purpose,
                expires_at=float(now) + CHALLENGE_TTL_SECONDS,
            )
            self._pending[ceremony_id] = pending
            return ceremony_id, pending

    def _consume(
        self, ceremony_id: str, owner_sub: str, session_id: str, purpose: str
    ) -> _PendingChallenge:
        if not isinstance(ceremony_id, str) or len(ceremony_id) != 32:
            raise PlatformAuthenticatorError("Platform ceremony is invalid or expired.")
        now = self._clock()
        with self._lock:
            pending = self._pending.pop(ceremony_id, None)
            if (
                pending is None or pending.owner_sub != owner_sub
                or pending.session_id != session_id or pending.purpose != purpose
                or isinstance(now, bool) or not isinstance(now, (int, float))
                or not math.isfinite(now) or float(now) >= pending.expires_at
            ):
                raise PlatformAuthenticatorError("Platform ceremony is invalid or expired.")
            return pending

    def _remove_expired(self, now: float) -> None:
        for key in [key for key, value in self._pending.items() if now >= value.expires_at]:
            self._pending.pop(key, None)

    @staticmethod
    def _validate_response_size(value: Any) -> None:
        try:
            encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            raise PlatformAuthenticatorError("Platform authenticator response is invalid.") from None
        if len(encoded) > MAX_CREDENTIAL_RESPONSE_BYTES:
            raise PlatformAuthenticatorError("Platform authenticator response is too large.")
