"""P5-515 negative/abuse/regression tests for the Phase 5 safety boundary.

All requests use synthetic inputs and FastAPI's in-process TestClient. No OS,
filesystem, process, registry, network, package-manager, or installer action is
available to these tests.
"""

from fastapi.testclient import TestClient

from agent_backend import policy, tools
from agent_backend.main import app
from agent_backend.security import MAX_REQUEST_BYTES

BASE_URL = "http://127.0.0.1:8000"
GOOD_ORIGIN = "http://127.0.0.1:4200"
GOOD_TOKEN = "a" * 64
GOOD_HEADERS = {
    "origin": GOOD_ORIGIN,
    "x-local-agent-token": GOOD_TOKEN,
}
PLAN_PAYLOAD = {"request": "Install Google Chrome", "language": "en"}
client = TestClient(app, base_url=BASE_URL, headers=GOOD_HEADERS)


def test_plans_endpoint_rejects_missing_and_invalid_local_token():
    for token in (None, "b" * 64):
        headers = {"origin": GOOD_ORIGIN}
        if token is not None:
            headers["x-local-agent-token"] = token
        response = TestClient(app, base_url=BASE_URL).post(
            "/api/plans", json=PLAN_PAYLOAD, headers=headers
        )
        assert response.status_code == 401


def test_plans_endpoint_rejects_foreign_origin_before_route_logic():
    response = client.post(
        "/api/plans",
        json=PLAN_PAYLOAD,
        headers={"origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Origin not allowed."}


def test_plans_endpoint_rejects_state_change_without_origin():
    response = TestClient(
        app, base_url=BASE_URL, headers={"x-local-agent-token": GOOD_TOKEN}
    ).post("/api/plans", json=PLAN_PAYLOAD)
    assert response.status_code == 403


def test_plans_endpoint_rejects_non_json_content_type():
    response = client.post(
        "/api/plans",
        content=b'{"request":"Install Google Chrome","language":"en"}',
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 415


def test_plans_endpoint_rejects_body_over_16_kib_before_parsing():
    response = client.post(
        "/api/plans",
        content=b"x" * (MAX_REQUEST_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}


def test_plans_endpoint_rejects_client_supplied_authority_and_execution_fields():
    response = client.post(
        "/api/plans",
        json={
            **PLAN_PAYLOAD,
            "risk_class": "R0",
            "required_permission": "P0",
            "approved": True,
            "execute": True,
            "handler": "shell",
        },
    )
    assert response.status_code == 422


def test_p1_plan_has_no_acknowledge_cancel_or_execute_route():
    created = client.post("/api/plans", json=PLAN_PAYLOAD)
    assert created.status_code == 200
    plan_id = created.json()["dry_run_plan"]["plan_id"]

    for method, path in (
        ("post", f"/api/plans/{plan_id}/acknowledgement"),
        ("post", f"/api/plans/{plan_id}/approve"),
        ("post", f"/api/plans/{plan_id}/cancel"),
        ("post", f"/api/plans/{plan_id}/execute"),
        ("post", "/api/execute"),
    ):
        response = getattr(client, method)(path, json={})
        assert response.status_code == 404


def test_plan_reference_is_opaque_and_unknown_reference_fails_closed():
    response = client.get("/api/plans/" + "f" * 32)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_denied_policy_never_invokes_spy_handler(monkeypatch):
    calls = []

    def spy_handler(request):
        calls.append(request)
        raise AssertionError("spy handler must not be invoked")

    monkeypatch.setattr(tools, "_HANDLERS", {"software.install": spy_handler})

    def deny(_tool_id):
        raise policy.PolicyDeniedError("permission_denied")

    monkeypatch.setattr(policy, "require_tool_allowed", deny)

    request = tools.ToolRequest(tool_id="software.install", target="Synthetic")
    try:
        tools.execute_tool(request)
    except policy.PolicyDeniedError as error:
        assert error.reason == "permission_denied"
    else:
        raise AssertionError("denied request unexpectedly succeeded")

    assert calls == []


def test_registered_tool_dispatch_remains_dry_run_only():
    result = tools.execute_tool(
        tools.ToolRequest(tool_id="software.install", target="Synthetic")
    )
    assert result.status == "dry_run"
    assert result.approval_required is True
    assert "no changes were made" in result.summary
