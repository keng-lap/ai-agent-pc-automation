"""Trusted-setup enrollment and encrypted storage for one TOTP authenticator.

The owner secret is protected with Windows DPAPI (current Windows user scope)
before it is written to the local file. Enrollment material is memory-only and
expires; the QR data URI is returned once and must never be logged or persisted.
Replacement requires a fresh Google OIDC authentication ceremony and verifies
the replacement TOTP before atomically replacing the existing secret.
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


class SecretStoreCommitUnknown(SecretStoreError):
    """Replacement committed, but its final state could not be verified."""


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
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        buffer = ctypes.create_string_buffer(value)
        source = cls._DataBlob(
            len(value),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        )
        target = cls._DataBlob()
        description = ctypes.c_wchar_p() if not protect else None
        try:
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
                function = crypt32.CryptUnprotectData
                function.argtypes = [
                    ctypes.POINTER(cls._DataBlob),
                    ctypes.POINTER(ctypes.c_wchar_p),
                    ctypes.POINTER(cls._DataBlob),
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    wintypes.DWORD,
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
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            cls._free_output_buffers(kernel32, target, description)

    @staticmethod
    def _free_output_buffers(kernel32, target, description=None) -> None:
        """Release every allocation returned by a DPAPI operation."""
        if target.pbData:
            kernel32.LocalFree(ctypes.cast(target.pbData, wintypes.HLOCAL))
        if description:
            kernel32.LocalFree(ctypes.cast(description, wintypes.HLOCAL))


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
            if os.name == "nt":
                try:
                    from .windows_secret_storage import WindowsSecretFile

                    return WindowsSecretFile(self._path).exists()
                except Exception as exc:  # noqa: BLE001 - diagnostic for fail-closed platform errors
                    raise SecretStoreError(
                        f"Secret store path is not trusted ({type(exc).__name__}: {exc})."
                    ) from None
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
            if os.name == "nt":
                try:
                    from .windows_secret_storage import WindowsSecretFile

                    WindowsSecretFile(self._path).create_exclusive(envelope)
                except FileExistsError:
                    raise SecretStoreError("An authenticator is already enrolled.") from None
                except Exception:  # noqa: BLE001 - sanitize platform failures
                    raise SecretStoreError("Encrypted authenticator storage failed.") from None
                return
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

    def replace(self, *, owner_sub: str, secret: str) -> None:
        """Atomically replace the enrolled authenticator after verified recovery."""
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
            if os.name == "nt":
                try:
                    from .windows_secret_storage import (
                        WindowsSecretFile,
                        WindowsSecretReplacementCommittedError,
                    )

                    WindowsSecretFile(self._path).replace(envelope)
                except WindowsSecretReplacementCommittedError:
                    raise SecretStoreCommitUnknown(
                        "Authenticator replacement committed but verification failed."
                    ) from None
                except Exception:  # noqa: BLE001 - sanitize platform failures
                    raise SecretStoreError("Authenticator recovery storage failed.") from None
                return
            if self._path.is_symlink() or not self._path.is_file():
                raise SecretStoreError("Existing authenticator storage is not trusted.")
            temporary = self._path.with_name(
                f".{self._path.name}.{secrets.token_hex(16)}.tmp"
            )
            descriptor = None
            try:
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    descriptor = None
                    stream.write(envelope)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self._path)
                if self._path.is_symlink() or not self._path.is_file():
                    raise OSError("replacement path is not a regular file")
            except OSError:
                if descriptor is not None:
                    os.close(descriptor)
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                raise SecretStoreError("Authenticator recovery storage failed.") from None

    def load(self, *, owner_sub: str) -> str | None:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            return None
        with self._lock:
            if os.name == "nt":
                try:
                    from .windows_secret_storage import WindowsSecretFile

                    envelope_bytes = WindowsSecretFile(self._path).read()
                except FileNotFoundError:
                    return None
                except Exception:  # noqa: BLE001 - sanitize platform failures
                    raise SecretStoreError("Encrypted authenticator storage is unavailable.") from None
            else:
                if self._path.is_symlink():
                    raise SecretStoreError("Secret store path is not trusted.")
                if not self._path.exists():
                    return None
                try:
                    envelope_bytes = self._path.read_bytes()
                except OSError:
                    raise SecretStoreError("Encrypted authenticator storage is unavailable.") from None
            try:
                envelope = json.loads(envelope_bytes.decode("ascii"))
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
                    or not isinstance(payload["owner_sub"], str)
                    or not isinstance(payload["secret"], str)
                ):
                    raise ValueError
                if payload["owner_sub"] != owner_sub:
                    return None
                code_at(payload["secret"], 0)
                return payload["secret"]
            except (OSError, ValueError, TypeError, KeyError, TotpConfigurationError):
                raise SecretStoreError("Encrypted authenticator storage is invalid.") from None
            except SecretStoreError:
                raise
            except Exception:  # noqa: BLE001 - sanitize platform protector failures
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
    monotonic_deadline: float
    replace_existing: bool = False
    failed_attempts: int = 0


class AuthenticatorEnrollmentManager:
    """One-owner, one-time QR enrollment state machine."""

    def __init__(
        self,
        *,
        secret_store: EncryptedTotpSecretFileStore,
        replay_guard: TotpReplayGuard | None = None,
        clock=None,
        monotonic_clock=None,
        secret_factory=generate_secret,
    ) -> None:
        self._secret_store = secret_store
        self._replay_guard = replay_guard or TotpReplayGuard()
        self._clock = clock or time.time
        self._monotonic_clock = monotonic_clock or (
            time.monotonic if clock is None else clock
        )
        self._secret_factory = secret_factory
        self._pending: dict[str, _PendingEnrollment] = {}
        self._lock = threading.RLock()

    def begin(self, *, owner_sub: str, account_name: str) -> EnrollmentStart:
        return self._begin(
            owner_sub=owner_sub,
            account_name=account_name,
            replace_existing=False,
        )

    def begin_recovery(self, *, owner_sub: str, account_name: str) -> EnrollmentStart:
        """Begin a Google-reauthenticated replacement without requiring the old TOTP."""
        return self._begin(
            owner_sub=owner_sub,
            account_name=account_name,
            replace_existing=True,
        )

    def _begin(
        self,
        *,
        owner_sub: str,
        account_name: str,
        replace_existing: bool,
    ) -> EnrollmentStart:
        if not isinstance(owner_sub, str) or not 1 <= len(owner_sub) <= 256:
            raise ValueError("authenticated owner is required")
        if not isinstance(account_name, str) or not 1 <= len(account_name.strip()) <= 254:
            raise ValueError("account label is invalid")
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            raise RuntimeError("system clock is invalid")

        monotonic_now = self._monotonic_clock()
        if (
            isinstance(monotonic_now, bool)
            or not isinstance(monotonic_now, (int, float))
            or not math.isfinite(monotonic_now)
            or monotonic_now < 0
        ):
            raise RuntimeError("elapsed-time clock is invalid")

        with self._lock:
            configured = self._secret_store.is_configured()
            if configured != replace_existing:
                if configured:
                    raise RuntimeError("an authenticator is already enrolled")
                raise RuntimeError("there is no authenticator to recover")
            # A refreshed/lost enrollment page cannot recover its one-time QR.
            # Starting again invalidates any older pending QR for this owner.
            superseded = [
                enrollment_id
                for enrollment_id, item in self._pending.items()
                if item.owner_sub == owner_sub
            ]
            for enrollment_id in superseded:
                self._pending.pop(enrollment_id, None)
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
                monotonic_deadline=float(monotonic_now) + ENROLLMENT_TTL_SECONDS,
                replace_existing=replace_existing,
            )
            return EnrollmentStart(
                enrollment_id=enrollment_id,
                qr_data_uri=qr_data_uri,
                expires_at=expires_at,
            )

    def confirm(
        self,
        *,
        enrollment_id: str,
        owner_sub: str,
        code: str,
        expected_replace_existing: bool | None = None,
    ) -> bool:
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
            or not isinstance(enrollment_id, str)
            or not isinstance(owner_sub, str)
        ):
            return False

        monotonic_now = self._monotonic_clock()
        if (
            isinstance(monotonic_now, bool)
            or not isinstance(monotonic_now, (int, float))
            or not math.isfinite(monotonic_now)
            or monotonic_now < 0
        ):
            return False

        with self._lock:
            pending = self._pending.get(enrollment_id)
            if pending is None or pending.owner_sub != owner_sub:
                return False
            if expected_replace_existing is not None and (
                type(expected_replace_existing) is not bool
                or pending.replace_existing is not expected_replace_existing
            ):
                return False
            if float(monotonic_now) >= pending.monotonic_deadline:
                self._pending.pop(enrollment_id, None)
                return False

            matched_step = matching_step(
                pending.secret,
                code,
                timestamp=float(now),
            )
            if matched_step is None:
                pending.failed_attempts += 1
                if pending.failed_attempts >= MAX_ENROLLMENT_ATTEMPTS:
                    self._pending.pop(enrollment_id, None)
                return False

            replay_owner = (
                f"{owner_sub}:recovery:{enrollment_id}"
                if pending.replace_existing
                else owner_sub
            )
            if not self._replay_guard.verify_and_consume(
                owner_key=replay_owner,
                secret=pending.secret,
                code=code,
                timestamp=float(now),
            ):
                pending.failed_attempts += 1
                if pending.failed_attempts >= MAX_ENROLLMENT_ATTEMPTS:
                    self._pending.pop(enrollment_id, None)
                return False

            try:
                if pending.replace_existing:
                    replay_committed = self._replay_guard.consume_step_after(
                        owner_key=owner_sub,
                        step=matched_step,
                        action=lambda: self._secret_store.replace(
                            owner_sub=owner_sub,
                            secret=pending.secret,
                        ),
                    )
                    if not replay_committed:
                        # A collision with the primary replay guard does not
                        # invalidate this QR. Keep it available for a later
                        # valid step, subject to the existing expiry/attempt cap.
                        pending.failed_attempts += 1
                        if pending.failed_attempts >= MAX_ENROLLMENT_ATTEMPTS:
                            self._pending.pop(enrollment_id, None)
                        return False
                else:
                    self._secret_store.save(owner_sub=owner_sub, secret=pending.secret)
            except SecretStoreCommitUnknown:
                # The file replacement may already be active. Burn the exact
                # matched step conservatively before reconciling the durable
                # secret, so a post-rename read failure cannot permit replay.
                self._replay_guard.consume_step_after(
                    owner_key=owner_sub,
                    step=matched_step,
                    action=lambda: None,
                )
                self._pending.pop(enrollment_id, None)
                try:
                    active_secret = self._secret_store.load(owner_sub=owner_sub)
                except SecretStoreError:
                    raise SecretStoreCommitUnknown(
                        "Authenticator replacement state remains unavailable."
                    ) from None
                return active_secret == pending.secret
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
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
