"""Privacy-minimized authentication audit events for F-516-01.

Events intentionally omit owner subjects, session IDs, plan IDs, action digests,
IP addresses, TOTP values, QR payloads, provisioning URIs and secret material.
The bounded sink is process-local diagnostics, not durable compliance storage.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

AuthAuditEventType = Literal[
    "auth.sign_in",
    "auth.enrollment",
    "auth.step_up",
]
AuthAuditOutcome = Literal["success", "denied"]
AuthAuditReason = Literal[
    "identity_invalid",
    "owner_not_allowlisted",
    "session_invalid",
    "authenticator_not_enrolled",
    "secret_store_unavailable",
    "invalid_totp",
    "replayed_totp",
    "challenge_expired",
    "action_binding_mismatch",
    "rate_limited",
    "trusted_setup_required",
    "invalid_software_approval",
]

MAX_AUTH_AUDIT_EVENTS = 500


class AuthAuditEvent(BaseModel):
    """Strict event schema containing only low-sensitivity allowlisted metadata."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    event_type: AuthAuditEventType
    occurred_at: datetime
    outcome: AuthAuditOutcome
    reason: AuthAuditReason | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("audit timestamp must be timezone-aware UTC")
        return value

    @field_validator("reason")
    @classmethod
    def reason_only_for_denials(cls, value, info):
        if value is not None and info.data.get("outcome") != "denied":
            raise ValueError("audit reason is permitted only for denied outcomes")
        return value


class AuthAuditEventSink:
    """Thread-safe FIFO buffer with a strict maximum retention count."""

    def __init__(self, *, capacity: int = MAX_AUTH_AUDIT_EVENTS) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_AUTH_AUDIT_EVENTS:
            raise ValueError("auth audit capacity must be between 1 and 500")
        self._events: deque[AuthAuditEvent] = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def record(self, event: AuthAuditEvent | dict[str, object]) -> None:
        validated = (
            event
            if isinstance(event, AuthAuditEvent)
            else AuthAuditEvent.model_validate(event)
        )
        with self._lock:
            self._events.append(validated)

    def record_optional(self, event: AuthAuditEvent | dict[str, object]) -> bool:
        try:
            self.record(event)
        except Exception:  # noqa: BLE001 - diagnostics must not alter the auth result
            return False
        return True

    def snapshot(self) -> tuple[AuthAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


AUTH_AUDIT_SINK = AuthAuditEventSink()


def record_auth_audit_event(
    *,
    event_type: AuthAuditEventType,
    outcome: AuthAuditOutcome,
    reason: AuthAuditReason | None = None,
) -> bool:
    """Record allowlisted authentication metadata without request or secret data."""
    try:
        event = AuthAuditEvent(
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            outcome=outcome,
            reason=reason,
        )
        return AUTH_AUDIT_SINK.record_optional(event)
    except Exception:  # noqa: BLE001 - optional diagnostics must never fail closed path
        return False
