"""WebAuthn ceremony primitives for local platform-authenticator enrollment.

The manager deliberately owns only short-lived ceremony state. Credential persistence
is supplied by the caller and must be committed before a credential is considered active.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

CeremonyPurpose = Literal["bootstrap", "recovery"]
CEREMONY_TTL_SECONDS = 180
MAX_PENDING_CEREMONIES = 32
MAX_CREDENTIAL_ID_BYTES = 1024
MAX_PUBLIC_KEY_BYTES = 4096


class WebAuthnCeremonyError(RuntimeError):
    """A WebAuthn ceremony could not be safely completed."""


@dataclass(frozen=True, slots=True)
class PendingCeremony:
    ceremony_id: str
    challenge: bytes
    user_handle: bytes
    owner_sub: str
    session_id: str
    purpose: CeremonyPurpose
    origin: str
    rp_id: str
    expires_at: float
    monotonic_deadline: float


@dataclass(frozen=True, slots=True)
class WebAuthnCredential:
    """Public credential material; private keys remain inside the authenticator."""

    credential_id: bytes
    public_key: bytes
    sign_count: int
    user_handle: bytes
    owner_sub: str
    transports: tuple[str, ...] = ()


class WebAuthnCeremonyStore:
    """Bounded, process-local, one-use challenge store bound to owner/session/purpose."""

    def __init__(self, *, clock=None, monotonic_clock=None) -> None:
        self._clock = clock or time.time
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._pending: dict[str, PendingCeremony] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
        rp_id: str,
    ) -> PendingCeremony:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            raise WebAuthnCeremonyError("Invalid ceremony owner.")
        if not isinstance(session_id, str) or not 16 <= len(session_id) <= 256:
            raise WebAuthnCeremonyError("Invalid ceremony session.")
        if purpose not in ("bootstrap", "recovery"):
            raise WebAuthnCeremonyError("Invalid ceremony purpose.")
        if not isinstance(origin, str) or not 1 <= len(origin) <= 512:
            raise WebAuthnCeremonyError("Invalid ceremony origin.")
        if not isinstance(rp_id, str) or not 1 <= len(rp_id) <= 253:
            raise WebAuthnCeremonyError("Invalid relying-party identifier.")

        now = self._clock()
        monotonic_now = self._monotonic_clock()
        if (
            isinstance(now, bool) or not isinstance(now, (int, float))
            or isinstance(monotonic_now, bool)
            or not isinstance(monotonic_now, (int, float))
        ):
            raise WebAuthnCeremonyError("Ceremony clock is invalid.")

        with self._lock:
            self._remove_expired(float(monotonic_now))
            if len(self._pending) >= MAX_PENDING_CEREMONIES:
                raise WebAuthnCeremonyError("Too many pending WebAuthn ceremonies.")
            ceremony = PendingCeremony(
                ceremony_id=secrets.token_urlsafe(24),
                challenge=secrets.token_bytes(32),
                user_handle=secrets.token_bytes(32),
                owner_sub=owner_sub,
                session_id=session_id,
                purpose=purpose,
                origin=origin,
                rp_id=rp_id,
                expires_at=float(now) + CEREMONY_TTL_SECONDS,
                monotonic_deadline=float(monotonic_now) + CEREMONY_TTL_SECONDS,
            )
            self._pending[ceremony.ceremony_id] = ceremony
            return ceremony

    def consume(
        self,
        ceremony_id: str,
        *,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
        rp_id: str,
    ) -> PendingCeremony:
        if not isinstance(ceremony_id, str) or not 16 <= len(ceremony_id) <= 128:
            raise WebAuthnCeremonyError("WebAuthn ceremony is unavailable.")
        now = self._monotonic_clock()
        with self._lock:
            ceremony = self._pending.pop(ceremony_id, None)
            if ceremony is None or now >= ceremony.monotonic_deadline:
                raise WebAuthnCeremonyError("WebAuthn ceremony is unavailable.")
            if (
                ceremony.owner_sub != owner_sub
                or ceremony.session_id != session_id
                or ceremony.purpose != purpose
                or ceremony.origin != origin
                or ceremony.rp_id != rp_id
            ):
                raise WebAuthnCeremonyError("WebAuthn ceremony binding mismatch.")
            return ceremony

    def _remove_expired(self, now: float) -> None:
        expired = [
            key for key, value in self._pending.items()
            if now >= value.monotonic_deadline
        ]
        for key in expired:
            self._pending.pop(key, None)


class WebAuthnPlatformAuthenticator:
    """Build and verify platform-only, user-verified WebAuthn ceremonies."""

    def __init__(
        self,
        *,
        rp_id: str,
        rp_name: str = "AI Agent PC",
        ceremony_store: WebAuthnCeremonyStore | None = None,
    ) -> None:
        if not isinstance(rp_id, str) or not 1 <= len(rp_id) <= 253:
            raise ValueError("A configured WebAuthn RP ID is required.")
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.ceremonies = ceremony_store or WebAuthnCeremonyStore()

    def begin_registration(
        self,
        *,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
    ) -> tuple[str, dict]:
        ceremony = self.ceremonies.create(
            owner_sub=owner_sub,
            session_id=session_id,
            purpose=purpose,
            origin=origin,
            rp_id=self.rp_id,
        )
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=ceremony.user_handle,
            user_name="Master User",
            user_display_name="Master User",
            challenge=ceremony.challenge,
            authenticator_selection=AuthenticatorSelectionCriteria(
                authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            timeout=CEREMONY_TTL_SECONDS * 1000,
        )
        return ceremony.ceremony_id, json.loads(options_to_json(options))

    def finish_registration(
        self,
        *,
        ceremony_id: str,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
        credential: dict,
    ) -> WebAuthnCredential:
        ceremony = self.ceremonies.consume(
            ceremony_id,
            owner_sub=owner_sub,
            session_id=session_id,
            purpose=purpose,
            origin=origin,
            rp_id=self.rp_id,
        )
        if not isinstance(credential, dict):
            raise WebAuthnCeremonyError("Invalid WebAuthn registration response.")
        try:
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=ceremony.challenge,
                expected_rp_id=self.rp_id,
                expected_origin=origin,
                require_user_verification=True,
            )
            credential_id = verification.credential_id
            public_key = verification.credential_public_key
            sign_count = verification.sign_count
            transports = credential.get("response", {}).get("transports", [])
            if (
                not isinstance(credential_id, bytes)
                or not 1 <= len(credential_id) <= MAX_CREDENTIAL_ID_BYTES
                or not isinstance(public_key, bytes)
                or not 1 <= len(public_key) <= MAX_PUBLIC_KEY_BYTES
                or type(sign_count) is not int
                or sign_count < 0
                or not isinstance(transports, list)
                or any(not isinstance(item, str) or len(item) > 32 for item in transports)
            ):
                raise ValueError("Invalid verified credential fields.")
        except Exception:
            raise WebAuthnCeremonyError("WebAuthn registration verification failed.") from None
        return WebAuthnCredential(
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            user_handle=ceremony.user_handle,
            owner_sub=owner_sub,
            transports=tuple(transports),
        )

    def begin_assertion(
        self,
        *,
        credential: WebAuthnCredential,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
    ) -> tuple[str, dict]:
        if credential.owner_sub != owner_sub:
            raise WebAuthnCeremonyError("Credential owner mismatch.")
        ceremony = self.ceremonies.create(
            owner_sub=owner_sub,
            session_id=session_id,
            purpose=purpose,
            origin=origin,
            rp_id=self.rp_id,
        )
        options = generate_authentication_options(
            rp_id=self.rp_id,
            challenge=ceremony.challenge,
            allow_credentials=[
                PublicKeyCredentialDescriptor(id=credential.credential_id)
            ],
            user_verification=UserVerificationRequirement.REQUIRED,
            timeout=CEREMONY_TTL_SECONDS * 1000,
        )
        return ceremony.ceremony_id, json.loads(options_to_json(options))

    def finish_assertion(
        self,
        *,
        ceremony_id: str,
        credential: WebAuthnCredential,
        owner_sub: str,
        session_id: str,
        purpose: CeremonyPurpose,
        origin: str,
        assertion: dict,
    ) -> int:
        ceremony = self.ceremonies.consume(
            ceremony_id,
            owner_sub=owner_sub,
            session_id=session_id,
            purpose=purpose,
            origin=origin,
            rp_id=self.rp_id,
        )
        if credential.owner_sub != owner_sub or not isinstance(assertion, dict):
            raise WebAuthnCeremonyError("WebAuthn credential is unavailable.")
        try:
            raw_id = assertion.get("rawId") or assertion.get("id")
            if not isinstance(raw_id, str):
                raise ValueError("Missing credential identifier.")
            supplied_id = _base64url_decode(raw_id)
            if not secrets.compare_digest(supplied_id, credential.credential_id):
                raise ValueError("Credential identifier mismatch.")
            response = assertion.get("response")
            if not isinstance(response, dict):
                raise ValueError("Missing assertion response.")
            supplied_handle = response.get("userHandle")
            if supplied_handle is not None and (
                not isinstance(supplied_handle, str)
                or not secrets.compare_digest(
                    _base64url_decode(supplied_handle), credential.user_handle
                )
            ):
                raise ValueError("Credential user handle mismatch.")
            verification = verify_authentication_response(
                credential=assertion,
                expected_challenge=ceremony.challenge,
                expected_rp_id=self.rp_id,
                expected_origin=origin,
                credential_public_key=credential.public_key,
                credential_current_sign_count=credential.sign_count,
                require_user_verification=True,
            )
            if verification.credential_id != credential.credential_id:
                raise ValueError("Verified credential identifier mismatch.")
            return verification.new_sign_count
        except Exception:
            raise WebAuthnCeremonyError("WebAuthn assertion verification failed.") from None


def _base64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid base64url value.")
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(value + padding)
    if not decoded:
        raise ValueError("Empty base64url value.")
    return decoded
