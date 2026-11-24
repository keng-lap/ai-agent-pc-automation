import json
import logging
from uuid import UUID

from agent_backend import runtime_diagnostics as diagnostics


def test_diagnostics_default_to_off_and_can_toggle_without_restart():
    diagnostics.set_enabled(False)

    assert diagnostics.is_enabled() is False
    assert diagnostics.set_enabled(True) is True
    assert diagnostics.is_enabled() is True
    assert diagnostics.set_enabled(False) is False
    assert diagnostics.is_enabled() is False


def test_correlation_id_accepts_valid_uuid_and_replaces_invalid_value():
    expected = "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21"

    assert diagnostics.correlation_id(expected) == str(UUID(expected))
    assert diagnostics.correlation_id("not-a-uuid") != "not-a-uuid"


def test_detailed_events_are_suppressed_when_diagnostics_are_off(caplog):
    diagnostics.set_enabled(False)

    with caplog.at_level(logging.INFO, logger="agent_backend.runtime_diagnostics"):
        diagnostics.emit_event(
            event_code="TEST_EVENT",
            component="backend",
            stage="test",
            correlation="6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21",
        )

    assert not caplog.records


def test_enabled_events_are_structured_and_exclude_sensitive_fields(caplog):
    diagnostics.set_enabled(True)
    try:
        with caplog.at_level(logging.INFO, logger="agent_backend.runtime_diagnostics"):
            diagnostics.emit_event(
                event_code="TEST_EVENT",
                component="backend",
                stage="manifest",
                correlation="6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21",
                fields={
                    "status_code": 503,
                    "authorization": "Bearer secret",
                    "totp_code": "123456",
                    "request_body": "must-not-be-recorded",
                },
            )

        payload = json.loads(caplog.records[-1].message)
        assert payload["event_code"] == "TEST_EVENT"
        assert payload["stage"] == "manifest"
        assert payload["fields"] == {"status_code": 503}
        assert "secret" not in caplog.records[-1].message
        assert "123456" not in caplog.records[-1].message
        assert "must-not-be-recorded" not in caplog.records[-1].message
    finally:
        diagnostics.set_enabled(False)
