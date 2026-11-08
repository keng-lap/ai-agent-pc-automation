"""Bounded, process-local security audit events (P5-513).

This sink is optional diagnostics only. It stores allowlisted metadata in memory;
it never persists prompts, secrets, raw parameters, plans, or machine inventory.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

AuditEventType = Literal[
    "policy.allowed",
    "policy.denied",
    "plan.created",
    "plan.rejected",
]
AuditToolId = Literal["software.install", "software.remove"]
AuditOutcome = Literal["allowed", "denied"]
AuditDenyReason = Literal[
    "unknown_tool",
    "risk_denied",
    "permission_denied",
    "execution_mode_denied",
    "handler_unavailable",
]

MAX_AUDIT_EVENTS = 500


class AuditEvent(BaseModel):
    """Strict allowlist for one security event; never contains request content."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    event_type: AuditEventType
    occurred_at: datetime
    tool_id: AuditToolId
    outcome: AuditOutcome
    deny_reason: AuditDenyReason | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("audit timestamp must be timezone-aware UTC")
        return value


class AuditEventSink:
    """Thread-safe FIFO event buffer; contents disappear with the process."""

    def __init__(self, *, capacity: int = MAX_AUDIT_EVENTS) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_AUDIT_EVENTS:
            raise ValueError("audit capacity must be between 1 and 500")
        self._capacity = capacity
        self._events: deque[AuditEvent] = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def record(self, event: AuditEvent | dict[str, object]) -> None:
        """Validate and append one event; invalid or extra fields are rejected."""
        validated = (
            event
            if isinstance(event, AuditEvent)
            else AuditEvent.model_validate(event)
        )
        with self._lock:
            self._events.append(validated)

    def record_optional(self, event: AuditEvent | dict[str, object]) -> bool:
        """Record optional diagnostics without changing the caller's safe path."""
        try:
            self.record(event)
        except Exception:  # noqa: BLE001 - optional audit must never break the safe path
            return False
        return True

    def snapshot(self) -> tuple[AuditEvent, ...]:
        """Return an immutable point-in-time view of retained events."""
        with self._lock:
            return tuple(self._events)

    def clear(self) -> None:
        """Clear all events; a new process naturally starts with an empty sink."""
        with self._lock:
            self._events.clear()


def make_audit_event(
    *,
    event_type: AuditEventType,
    tool_id: AuditToolId,
    outcome: AuditOutcome,
    deny_reason: AuditDenyReason | None = None,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    """Build a bounded event using backend time unless a test clock is supplied."""
    return AuditEvent(
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(UTC),
        tool_id=tool_id,
        outcome=outcome,
        deny_reason=deny_reason,
    )



# One process-local sink is shared by the approved runtime event producers.
# It is intentionally not exposed through an HTTP endpoint or persisted.
AUDIT_SINK = AuditEventSink()


def record_optional_audit_event(
    *,
    event_type: AuditEventType,
    tool_id: AuditToolId,
    outcome: AuditOutcome,
    deny_reason: AuditDenyReason | None = None,
) -> bool:
    """Record allowlisted runtime metadata without affecting the safe operation."""
    try:
        event = make_audit_event(
            event_type=event_type,
            tool_id=tool_id,
            outcome=outcome,
            deny_reason=deny_reason,
        )
        return AUDIT_SINK.record_optional(event)
    except Exception:  # noqa: BLE001 - optional audit must never affect the safe path
        return False
