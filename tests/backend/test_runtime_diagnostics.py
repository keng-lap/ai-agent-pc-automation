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


def test_diagnostics_control_api_changes_mode_immediately(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent_backend.auth_api import require_session
    from agent_backend import diagnostics_api

    monkeypatch.setattr(diagnostics_api, "store_available", lambda: True)
    diagnostics.set_enabled(False)
    app = FastAPI()
    app.include_router(diagnostics_api.router)
    app.dependency_overrides[require_session] = lambda: object()
    client = TestClient(app)

    assert client.get("/api/diagnostics").json() == {"enabled": False, "storage_available": True}
    enabled = client.put("/api/diagnostics", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json() == {"enabled": True, "storage_available": True}
    assert client.get("/api/diagnostics").json() == {"enabled": True, "storage_available": True}

    disabled = client.put("/api/diagnostics", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False, "storage_available": True}
    assert client.get("/api/diagnostics").json() == {"enabled": False, "storage_available": True}


def test_browser_event_api_is_disabled_by_default_and_accepts_allowlisted_events(caplog):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from agent_backend.auth_api import require_session
    from agent_backend.diagnostics_api import router

    diagnostics.set_enabled(False)
    app = FastAPI()

    @app.middleware("http")
    async def add_correlation(request: Request, call_next):
        request.state.correlation_id = "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_session] = lambda: object()
    client = TestClient(app)

    disabled = client.post(
        "/api/diagnostics/browser-events",
        json={"event_code": "BROWSER_API_FAILURE", "component": "api", "status_code": 503},
    )
    assert disabled.status_code == 409

    diagnostics.set_enabled(True)
    try:
        with caplog.at_level(logging.ERROR, logger="agent_backend.runtime_diagnostics"):
            response = client.post(
                "/api/diagnostics/browser-events",
                json={
                    "event_code": "BROWSER_UNCAUGHT_ERROR",
                    "component": "browser",
                    "error_type": "TypeError",
                    "stack": "120:8|124:12",
                },
            )
        assert response.status_code == 200
        assert response.json() == {"recorded": True}
        event = json.loads(caplog.records[-1].message)
        assert event["correlation_id"] == "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21"
        assert event["event_code"] == "BROWSER_UNCAUGHT_ERROR"
        assert event["fields"] == {"error_type": "TypeError", "stack": "120:8|124:12"}
    finally:
        diagnostics.set_enabled(False)


def test_exception_events_include_safe_stack_without_exception_message(caplog):
    diagnostics.set_enabled(True)
    try:
        try:
            raise ValueError("private message containing a secret")
        except ValueError as error:
            with caplog.at_level(logging.ERROR, logger="agent_backend.runtime_diagnostics"):
                diagnostics.emit_exception(
                    event_code="TEST_EXCEPTION",
                    component="backend",
                    stage="test",
                    correlation="6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21",
                    error=error,
                )

        payload = json.loads(caplog.records[-1].message)
        assert payload["fields"]["exception_type"] == "ValueError"
        assert "test_exception_events_include_safe_stack" in payload["fields"]["stack"]
        assert "private message" not in caplog.records[-1].message
    finally:
        diagnostics.set_enabled(False)


def test_diagnostics_store_persists_and_exports_bounded_structured_events(tmp_path):
    store = diagnostics.RuntimeDiagnosticsStore(tmp_path / "diagnostics" / "runtime.sqlite3")
    try:
        event = {
            "timestamp": "2026-11-24T00:00:00+00:00",
            "severity": "ERROR",
            "event_code": "MANIFEST_SOURCE_UNAVAILABLE_OR_INVALID",
            "component": "manifest",
            "stage": "manifest_validation",
            "correlation_id": "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21",
            "fields": {"status_code": 503},
        }
        store.append(event)
        assert store.export_recent() == [event]
    finally:
        store.close()


def test_diagnostics_export_returns_ndjson_without_enabling_collection(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent_backend.auth_api import require_session
    from agent_backend import diagnostics_api

    sample = [{
        "timestamp": "2026-11-24T00:00:00+00:00",
        "severity": "ERROR",
        "event_code": "MANIFEST_SOURCE_UNAVAILABLE_OR_INVALID",
        "component": "manifest",
        "stage": "manifest_validation",
        "correlation_id": "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21",
        "fields": {"status_code": 503},
    }]
    monkeypatch.setattr(diagnostics_api, "export_recent_events", lambda limit: sample)
    monkeypatch.setattr(diagnostics_api, "store_available", lambda: True)
    app = FastAPI()
    app.include_router(diagnostics_api.router)
    app.dependency_overrides[require_session] = lambda: object()
    response = TestClient(app).get("/api/diagnostics/export?limit=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.text.count("MANIFEST_SOURCE_UNAVAILABLE_OR_INVALID") == 1
    assert '"status_code":503' in response.text


def test_diagnostics_cannot_be_enabled_without_persistent_storage(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent_backend.auth_api import require_session
    from agent_backend import diagnostics_api

    monkeypatch.setattr(diagnostics_api, "store_available", lambda: False)
    diagnostics.set_enabled(False)
    app = FastAPI()
    app.include_router(diagnostics_api.router)
    app.dependency_overrides[require_session] = lambda: object()

    response = TestClient(app).put("/api/diagnostics", json={"enabled": True})

    assert response.status_code == 503
    assert diagnostics.is_enabled() is False


def test_browser_event_api_rejects_raw_stack_paths_and_messages():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent_backend.auth_api import require_session
    from agent_backend.diagnostics_api import router

    diagnostics.set_enabled(True)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_session] = lambda: object()
    response = TestClient(app).post(
        "/api/diagnostics/browser-events",
        json={
            "event_code": "BROWSER_UNCAUGHT_ERROR",
            "component": "browser",
            "error_type": "TypeError",
            "stack": "https://example.test/main.js?token=secret",
        },
    )
    diagnostics.set_enabled(False)

    assert response.status_code == 422
