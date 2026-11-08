"""Trusted-setup enrollment and encrypted storage for one TOTP authenticator.

The owner secret is protected with Windows DPAPI (current Windows user scope)
before it is written to the local file. Enrollment material is memory-only and
expires; the QR data URI is returned once and must never be logged or persisted.
No lost-device replacement or recovery path is provided by this module.
"""

from __future__ import annotations

import base64
import ctypes
import json
import math
import os
import secrets
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

import qrcode
from qrcode.image.svg import SvgPathImage

from .totp import (
    TotpConfigurationError,
    TotpReplayGuard,
    code_at,
    generate_secret,
    matching_step,
    provisioning_uri,
)

ENROLLMENT_TTL_SECONDS = 300
MAX_ENROLLMENT_ATTEMPTS = 5
ENROLLMENT_ISSUER = "AI Agent PC"


class SecretStoreError(RuntimeError):
    """Raised when encrypted authenticator secret storage fails."""


class SecretProtector(Protocol):
    """Platform protection adapter for the encrypted secret file."""

    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class WindowsDpapiProtector:
    """Protect bytes using Windows DPAPI for the current Windows user."""

    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def protect(self, plaintext: bytes) -> bytes:
        return self._transform(plaintext, protect=True)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._transform(ciphertext, protect=False)

    @classmethod
    def _transform(cls, value: bytes, *, protect: bool) -> bytes:
        if os.name != "nt":
            raise SecretStoreError("Windows DPAPI is available only on Windows.")
        if not isinstance(value, bytes) or not value:
            raise SecretStoreError("Invalid secret payload.")

        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        buffer = ctypes.create_string_buffer(value)
        source = cls._DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        target = cls._DataBlob()
        if protect:
            function = crypt32.CryptProtectData
            function.argtypes = [
                ctypes.POINTER(cls._DataBlob),
                ctypes.c_wchar_p,
                ctypes.POINTER(cls._DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.POINTER(cls._DataBlob),
            ]
            succeeded = function(
                ctypes.byref(source),
                "AI Agent TOTP authenticator",
                None,
                None,
                None,
                cls._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(target),
            )
        else:
            description = ctypes.c_wchar_p()
            function = crypt32.CryptUnprotectData
            function.argtypes = [
                ctypes.POINTER(cls._DataBlob),
                ctypes.POINTER(ctypes.c_wchar_p),
                ctypes.POINTER(cls._DataBlob),
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.wintypes.DWORD,
                ctypes.POINTER(cls._DataBlob),
            ]
            succeeded = function(
                ctypes.byref(source),
                ctypes.byref(description),
                None,
                None,
                None,
                cls._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(target),
            )
        if not succeeded:
            raise SecretStoreError("Windows secret protection operation failed.")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            kernel32.LocalFree(target.pbData)


class EncryptedTotpSecretFileStore:
    """Store exactly one DPAPI-protected owner secret in a local file."""

    def __init__(self, path: Path, protector: SecretProtector) -> None:
        if not isinstance(path, Path):
            raise TypeError("secret store path must be a pathlib.Path")
        self._path = path
        self._protector = protector
        self._lock = threading.RLock()

    def is_configured(self) -> bool:
        with self._lock:
            if self._path.is_symlink():
                raise SecretStoreError("Secret store path is not trusted.")
            return self._path.exists()

    def save(self, *, owner_sub: str, secret: str) -> None:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            raise SecretStoreError("Invalid owner identity.")
        try:
            code_at(secret, 0)
            plaintext = json.dumps(
                {"owner_sub": owner_sub, "secret": secret},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            ciphertext = self._protector.protect(plaintext)
            if not isinstance(ciphertext, bytes) or not ciphertext:
                raise SecretStoreError("Secret protection returned invalid data.")
            envelope = json.dumps(
                {
                    "version": 1,
                    "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        except (TotpConfigurationError, TypeError, ValueError):
            raise SecretStoreError("Authenticator secret could not be stored.") from None

        with self._lock:
            if self._path.is_symlink():
                raise SecretStoreError("Secret store path is not trusted.")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(
                    self._path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                raise SecretStoreError("An authenticator is already enrolled.") from None
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(envelope)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError:
                try:
                    self._path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise SecretStoreError("Encrypted authenticator storage failed.") from None

    def load(self, *, owner_sub: str) -> str | None:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            return None
        with self._lock:
            if self._path.is_symlink():
                raise SecretStoreError("Secret store path is not trusted.")
            if not self._path.exists():
                return None
            try:
                envelope = json.loads(self._path.read_text(encoding="ascii"))
                if (
                    not isinstance(envelope, dict)
                    or set(envelope) != {"version", "ciphertext"}
                    or envelope["version"] != 1
                    or not isinstance(envelope["ciphertext"], str)
                ):
                    raise ValueError
                ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
                plaintext = self._protector.unprotect(ciphertext)
                payload = json.loads(plaintext.decode("utf-8"))
                if (
                    not isinstance(payload, dict)
                    or set(payload) != {"owner_sub", "secret"}
                    or payload["owner_sub"] != owner_sub
                    or not isinstance(payload["secret"], str)
                ):
                    raise ValueError
                code_at(payload["secret"], 0)
                return payload["secret"]
            except (OSError, ValueError, TypeError, KeyError, TotpConfigurationError):
                raise SecretStoreError("Encrypted authenticator storage is invalid.") from None
            except SecretStoreError:
                raise
            except Exception:
                raise SecretStoreError("Encrypted authenticator storage is unavailable.") from None


@dataclass(frozen=True, slots=True)
class EnrollmentStart:
    """One-time QR material returned to the trusted-setup UI."""

    enrollment_id: str
    qr_data_uri: str
    expires_at: float


@dataclass(slots=True)
class _PendingEnrollment:
    owner_sub: str
    secret: str
    expires_at: float
    failed_attempts: int = 0


class AuthenticatorEnrollmentManager:
    """One-owner, one-time QR enrollment state machine."""

    def __init__(
        self,
        *,
        secret_store: EncryptedTotpSecretFileStore,
        replay_guard: TotpReplayGuard | None = None,
        clock=None,
        secret_factory=generate_secret,
    ) -> None:
        self._secret_store = secret_store
        self._replay_guard = replay_guard or TotpReplayGuard()
        self._clock = clock or time.time
        self._secret_factory = secret_factory
        self._pending: dict[str, _PendingEnrollment] = {}
        self._lock = threading.RLock()

    def begin(self, *, owner_sub: str, account_name: str) -> EnrollmentStart:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            raise ValueError("authenticated owner is required")
        if not isinstance(account_name, str) or not 1 <= len(account_name.strip()) <= 254:
            raise ValueError("account label is invalid")
        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now)
            or now < 0:
            raise RuntimeError("system clock is invalid")

        with self._lock:
            if self._secret_store.is_configured():
                raise RuntimeError("an authenticator is already enrolled")
            if any(item.owner_sub == owner_sub for item in self._pending.values()):
                raise RuntimeError("an enrollment is already pending")
            secret = self._secret_factory()
            uri = provisioning_uri(
                secret,
                account_name=account_name,
                issuer=ENROLLMENT_ISSUER,
            )
            qr_data_uri = _qr_data_uri(uri)
            enrollment_id = secrets.token_hex(16)
            expires_at = float(now) + ENROLLMENT_TTL_SECONDS
            self._pending[enrollment_id] = _PendingEnrollment(
                owner_sub=owner_sub,
                secret=secret,
                expires_at=expires_at,
            )
            return EnrollmentStart(
                enrollment_id=enrollment_id,
                qr_data_uri=qr_data_uri,
                expires_at=expires_at,
            )

    def confirm(self, *, enrollment_id: str, owner_sub: str, code: str) -> bool:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or now < 0
            or not isinstance(enrollment_id, str)
            or not isinstance(owner_sub, str)
        ):
            return False

        with self._lock:
            pending = self._pending.get(enrollment_id)
            if pending is None or pending.owner_sub != owner_sub:
                return False
            if now >= pending.expires_at:
                self._pending.pop(enrollment_id, None)
                return False

            if matching_step(pending.secret, code, timestamp=float(now)) is None:
                pending.failed_attempts += 1
                if pending.failed_attempts >= MAX_ENROLLMENT_ATTEMPTS:
                    self._pending.pop(enrollment_id, None)
                return False

            if not self._replay_guard.verify_and_consume(
                owner_key=owner_sub,
                secret=pending.secret,
                code=code,
                timestamp=float(now),
            ):
                pending.failed_attempts += 1
                if pending.failed_attempts >= MAX_ENROLLMENT_ATTEMPTS:
                    self._pending.pop(enrollment_id, None)
                return False

            try:
                self._secret_store.save(owner_sub=owner_sub, secret=pending.secret)
            except SecretStoreError:
                self._pending.pop(enrollment_id, None)
                return False
            self._pending.pop(enrollment_id, None)
            return True


def _qr_data_uri(provisioning_uri_value: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=4,
    )
    qr.add_data(provisioning_uri_value)
    qr.make(fit=True)
    image = qr.make_image(image_factory=SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
