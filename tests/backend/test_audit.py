from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from agent_backend.audit import (
    MAX_AUDIT_EVENTS,
    AUDIT_SINK,
    AuditEvent,
    AuditEventSink,
    make_audit_event,
    record_optional_audit_event,
)


def event(index=0):
    return make_audit_event(
        event_type="plan.created",
        tool_id="software.install",
        outcome="allowed",
        occurred_at=datetime.fromtimestamp(index, UTC),
    )


def test_event_schema_is_strict_and_immutable():
    item = event()
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**item.model_dump(), "prompt": "install Chrome"})
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**item.model_dump(), "token": "secret"})
    with pytest.raises(ValidationError):
        item.outcome = "denied"


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "arbitrary.event"},
        {"tool_id": "unknown.tool"},
        {"outcome": "maybe"},
        {"deny_reason": "raw exception text"},
    ],
)
def test_event_rejects_values_outside_allowlists(change):
    with pytest.raises(ValidationError):
        AuditEvent.model_validate({**event().model_dump(), **change})


def test_event_requires_utc_aware_timestamp():
    with pytest.raises(ValidationError, match="UTC"):
        AuditEvent(
            event_type="plan.created",
            occurred_at=datetime(2026, 11, 7),
            tool_id="software.install",
            outcome="allowed",
        )


def test_sink_evicts_oldest_event_at_capacity():
    sink = AuditEventSink(capacity=2)
    first, second, third = event(1), event(2), event(3)

    sink.record(first)
    sink.record(second)
    sink.record(third)

    assert sink.snapshot() == (second, third)


def test_sink_default_capacity_is_bounded_to_500():
    sink = AuditEventSink()
    for index in range(MAX_AUDIT_EVENTS + 1):
        sink.record(event(index))

    retained = sink.snapshot()
    assert len(retained) == MAX_AUDIT_EVENTS
    assert retained[0].occurred_at == datetime.fromtimestamp(1, UTC)


@pytest.mark.parametrize("capacity", [0, -1, 501, True])
def test_sink_rejects_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        AuditEventSink(capacity=capacity)


def test_optional_diagnostics_failure_is_non_blocking():
    sink = AuditEventSink()

    assert sink.record_optional(
        {**event().model_dump(), "raw_parameters": {"x": 1}}
    ) is False
    assert sink.snapshot() == ()


def test_new_sink_starts_empty_and_clear_removes_events():
    first_process = AuditEventSink()
    first_process.record(event())

    restarted_process = AuditEventSink()
    assert restarted_process.snapshot() == ()

    first_process.clear()
    assert first_process.snapshot() == ()



def test_unavailable_optional_audit_sink_does_not_block_safe_path(monkeypatch):
    sink = AuditEventSink()
    safe_path_calls = []

    def unavailable(_event):
        raise OSError("synthetic sink unavailable")

    monkeypatch.setattr(sink, "record", unavailable)

    recorded = sink.record_optional(event())
    safe_path_calls.append("continued")

    assert recorded is False
    assert safe_path_calls == ["continued"]
    assert sink.snapshot() == ()



def test_optional_audit_rejects_unknown_tool_without_raising():
    AUDIT_SINK.clear()

    assert record_optional_audit_event(
        event_type="policy.denied",
        tool_id="shell.run",
        outcome="denied",
        deny_reason="unknown_tool",
    ) is False
    assert AUDIT_SINK.snapshot() == ()
