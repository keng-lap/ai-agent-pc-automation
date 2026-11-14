from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_backend.auth_audit import (
    AUTH_AUDIT_SINK,
    AuthAuditEvent,
    AuthAuditEventSink,
    record_auth_audit_event,
)


def event(index=0, **changes):
    values = {
        "event_type": "auth.step_up",
        "occurred_at": datetime.fromtimestamp(index, UTC),
        "outcome": "denied",
        "reason": "invalid_totp",
    }
    values.update(changes)
    return AuthAuditEvent(**values)


def test_auth_audit_schema_is_strict_and_immutable():
    item = event()
    with pytest.raises(ValidationError):
        AuthAuditEvent.model_validate({**item.model_dump(), "totp": "123456"})
    with pytest.raises(ValidationError):
        AuthAuditEvent.model_validate({**item.model_dump(), "owner_sub": "sensitive"})
    with pytest.raises(ValidationError):
        item.outcome = "success"


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "unknown.event"},
        {"outcome": "maybe"},
        {"reason": "raw exception text"},
        {"reason": "invalid_totp", "outcome": "success"},
    ],
)
def test_auth_audit_rejects_values_outside_allowlists(change):
    with pytest.raises(ValidationError):
        AuthAuditEvent.model_validate({**event().model_dump(), **change})


def test_auth_audit_requires_utc_timestamp():
    with pytest.raises(ValidationError, match="UTC"):
        AuthAuditEvent(
            event_type="auth.sign_in",
            occurred_at=datetime(2026, 11, 8),
            outcome="success",
        )


def test_auth_audit_sink_is_bounded():
    sink = AuthAuditEventSink(capacity=2)
    sink.record(event(1))
    sink.record(event(2))
    sink.record(event(3))

    retained = sink.snapshot()
    assert len(retained) == 2
    assert retained[0].occurred_at == datetime.fromtimestamp(2, UTC)


@pytest.mark.parametrize("capacity", [0, -1, 501, True])
def test_auth_audit_sink_rejects_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        AuthAuditEventSink(capacity=capacity)


def test_optional_auth_audit_failure_does_not_block_auth_flow(monkeypatch):
    sink = AuthAuditEventSink()

    def unavailable(_event):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(sink, "record", unavailable)
    assert sink.record_optional(event()) is False
    assert sink.snapshot() == ()


def test_global_auth_audit_records_only_safe_fields():
    AUTH_AUDIT_SINK.clear()

    assert record_auth_audit_event(
        event_type="auth.sign_in",
        outcome="denied",
        reason="owner_not_allowlisted",
    )
    saved = AUTH_AUDIT_SINK.snapshot()
    assert len(saved) == 1
    assert saved[0].model_dump().keys() == {
        "event_type",
        "occurred_at",
        "outcome",
        "reason",
    }


def test_software_approval_denial_reason_is_recorded():
    AUTH_AUDIT_SINK.clear()

    assert record_auth_audit_event(
        event_type="auth.step_up",
        outcome="denied",
        reason="invalid_software_approval",
    )
    saved = AUTH_AUDIT_SINK.snapshot()
    assert len(saved) == 1
    assert saved[0].reason == "invalid_software_approval"
