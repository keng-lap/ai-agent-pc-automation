"""Provider-independent RFC 6238 TOTP primitives for the F-516-01 step-up flow.

This module deliberately contains no HTTP routes, identity provider, persistence,
or machine-execution integration. Replay protection is process-local and must be
replaced by a durable atomic store before multi-worker/production use.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import math
import secrets
import threading
import time
from collections.abc import Callable
from urllib.parse import quote

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_WINDOW_STEPS = 1
TOTP_SECRET_BYTES = 20
TOTP_ALGORITHM = "SHA1"


class TotpConfigurationError(ValueError):
    """Raised when a TOTP secret or provisioning identity is invalid."""


def generate_secret() -> str:
    """Generate a 160-bit random Base32 secret suitable for RFC 6238."""
    return base64.b32encode(secrets.token_bytes(TOTP_SECRET_BYTES)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    if not isinstance(secret, str) or not secret or len(secret) > 128:
        raise TotpConfigurationError("Invalid TOTP secret.")
    normalized = secret.upper()
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in normalized):
        raise TotpConfigurationError("Invalid TOTP secret.")
    padded = normalized + ("=" * ((8 - len(normalized) % 8) % 8))
    try:
        decoded = base64.b32decode(padded, casefold=False)
    except (binascii.Error, ValueError):
        raise TotpConfigurationError("Invalid TOTP secret.") from None
    if len(decoded) < 16:
        raise TotpConfigurationError("TOTP secret must contain at least 128 bits.")
    return decoded


def provisioning_uri(secret: str, *, account_name: str, issuer: str) -> str:
    """Build an otpauth URI; callers must display it once and never persist/log it."""
    _decode_secret(secret)
    if (
        not isinstance(account_name, str)
        or not account_name.strip()
        or len(account_name) > 254
        or not isinstance(issuer, str)
        or not issuer.strip()
        or len(issuer) > 64
    ):
        raise TotpConfigurationError("Invalid TOTP provisioning identity.")
    label = f"{issuer.strip()}:{account_name.strip()}"
    return (
        f"otpauth://totp/{quote(label, safe='')}"
        f"?secret={quote(secret, safe='')}&issuer={quote(issuer.strip(), safe='')}"
        f"&algorithm={TOTP_ALGORITHM}&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )


def code_at(secret: str, timestamp: float) -> str:
    """Return the six-digit RFC 6238 code for a timestamp (test/support helper)."""
    key = _decode_secret(secret)
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise TypeError("timestamp must be a finite number")
    if not math.isfinite(timestamp) or timestamp < 0:
        raise ValueError("timestamp must be a finite non-negative number")
    counter = int(timestamp) // TOTP_PERIOD_SECONDS
    message = counter.to_bytes(8, byteorder="big", signed=False)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
    return f"{binary % (10**TOTP_DIGITS):0{TOTP_DIGITS}d}"


def matching_step(
    secret: str,
    code: str,
    *,
    timestamp: float,
    window_steps: int = TOTP_WINDOW_STEPS,
) -> int | None:
    """Return the matched counter step within the bounded clock-skew window."""
    if (
        not isinstance(code, str)
        or len(code) != TOTP_DIGITS
        or not code.isascii()
        or not code.isdigit()
        or isinstance(window_steps, bool)
        or not isinstance(window_steps, int)
        or not 0 <= window_steps <= TOTP_WINDOW_STEPS
    ):
        return None
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(timestamp)
        or timestamp < 0
    ):
        return None

    try:
        _decode_secret(secret)
    except TotpConfigurationError:
        return None

    current_step = int(timestamp) // TOTP_PERIOD_SECONDS
    matches: list[int] = []
    for step in range(current_step - window_steps, current_step + window_steps + 1):
        if step < 0:
            continue
        expected = code_at(secret, step * TOTP_PERIOD_SECONDS)
        if hmac.compare_digest(expected, code):
            matches.append(step)
    if not matches:
        return None
    return min(matches, key=lambda step: (abs(step - current_step), -step))


class TotpReplayGuard:
    """Thread-safe, process-local one-use-per-time-step guard.

    The caller supplies a stable owner key. A production multi-worker deployment
    must use a shared store with an atomic compare-and-set/unique constraint.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock
        self._last_consumed: dict[str, int] = {}
        self._lock = threading.Lock()

    def verify_and_consume(
        self,
        *,
        owner_key: str,
        secret: str,
        code: str,
        timestamp: float | None = None,
    ) -> bool:
        if not isinstance(owner_key, str) or not owner_key or len(owner_key) > 256:
            return False
        if timestamp is None:
            if self._clock is not None:
                timestamp = self._clock()
            else:
                import time

                timestamp = time.time()
        step = matching_step(secret, code, timestamp=timestamp)
        if step is None:
            return False
        with self._lock:
            previous = self._last_consumed.get(owner_key)
            if previous is not None and step <= previous:
                return False
            self._last_consumed[owner_key] = step
            return True

    def verify_and_consume_with_secret_loader(
        self,
        *,
        owner_key: str,
        secret_loader: Callable[[], str | None],
        code: str,
        timestamp: float | None = None,
    ) -> bool:
        """Load the current secret and consume its code under one replay lock."""
        if (
            not isinstance(owner_key, str)
            or not owner_key
            or len(owner_key) > 256
            or not callable(secret_loader)
        ):
            return False
        if timestamp is None:
            if self._clock is not None:
                timestamp = self._clock()
            else:
                import time

                timestamp = time.time()
        with self._lock:
            # Secret replacement uses this same lock. A caller therefore sees
            # either the old secret before replacement or the new secret after
            # replacement, never a stale pre-lock snapshot.
            secret = secret_loader()
            if not isinstance(secret, str) or not secret:
                return False
            step = matching_step(secret, code, timestamp=timestamp)
            if step is None:
                return False
            previous = self._last_consumed.get(owner_key)
            if previous is not None and step <= previous:
                return False
            self._last_consumed[owner_key] = step
            return True

    def consume_step_after(
        self,
        *,
        owner_key: str,
        step: int,
        action: Callable[[], None],
        consume_on_exception: tuple[type[Exception], ...] = (),
    ) -> bool:
        """Run an operation and consume its exact TOTP step atomically.

        The replay lock is held while the operation runs, so concurrent
        Step-up verification cannot consume a code between secret replacement
        and replay-state advancement. Exceptions listed in
        ``consume_on_exception`` burn the step before the lock is released;
        other failures leave replay state unchanged.
        """
        if (
            not isinstance(owner_key, str)
            or not owner_key
            or len(owner_key) > 256
            or isinstance(step, bool)
            or not isinstance(step, int)
            or step < 0
            or not callable(action)
            or not isinstance(consume_on_exception, tuple)
            or any(
                not isinstance(kind, type) or not issubclass(kind, Exception)
                for kind in consume_on_exception
            )
        ):
            return False
        with self._lock:
            previous = self._last_consumed.get(owner_key)
            if previous is not None and step <= previous:
                return False
            try:
                action()
            except Exception as exc:
                if isinstance(exc, consume_on_exception):
                    self._last_consumed[owner_key] = step
                raise
            self._last_consumed[owner_key] = step
            return True

    def block_through_current_step(
        self,
        *,
        owner_key: str,
        timestamp: float | None = None,
    ) -> None:
        """Block the current and all earlier codes after a process restart.

        The replay cache itself is process-local. Seeding it from the current
        time step prevents a code from the immediately preceding process from
        being replayed after restart while the same RFC 6238 time step remains
        acceptable.
        """
        if not isinstance(owner_key, str) or not owner_key or len(owner_key) > 256:
            raise TotpConfigurationError("Invalid TOTP owner key.")
        if timestamp is None:
            timestamp = self._clock() if self._clock is not None else time.time()
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp < 0
        ):
            raise TotpConfigurationError("Invalid TOTP timestamp.")
        current_step = int(timestamp // TOTP_PERIOD_SECONDS)
        with self._lock:
            previous = self._last_consumed.get(owner_key)
            if previous is None or current_step > previous:
                self._last_consumed[owner_key] = current_step

    def clear(self) -> None:
        """Clear process-local replay state; intended for isolated tests only."""
        with self._lock:
            self._last_consumed.clear()
