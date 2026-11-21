from fastapi.testclient import TestClient

from agent_backend.main import app

client = TestClient(
    app,
    base_url="http://127.0.0.1:8000",
    headers={
        "origin": "http://127.0.0.1:4200",
        "x-local-agent-token": "a" * 64,
    },
)


def test_java_development_request_returns_questions_without_install_preview():
    response = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request"] == "เตรียมเครื่องพัฒนา Java"
    assert body["interpretation"]["category"] == "development_task"
    assert body["interpretation"]["target"] == "Java"
    assert body["dry_run_plan"] is None
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert body["notice"] == "PLAN_REVIEW_ONLY_NO_EXECUTION"
    assert body["questions"] == [
        "ต้องการ JDK เวอร์ชันใด (เช่น 21 LTS)?",
        "ต้องการใช้ IDE ใด หรือให้แนะนำตัวเลือกก่อน?",
    ]

def test_plan_can_be_read_by_opaque_id_from_process_store():
    created = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    )
    assert created.status_code == 200
    plan_id = created.json()["dry_run_plan"]["plan_id"]

    fetched = client.get(f"/api/plans/{plan_id}")
    assert fetched.status_code == 200
    assert fetched.json()["plan_id"] == plan_id
    assert fetched.json()["live_checks_performed"] is False


def test_plan_request_rejects_client_supplied_policy_fields():
    response = client.post(
        "/api/plans",
        json={
            "request": "Install Google Chrome",
            "language": "en",
            "risk_class": "R0",
            "approved": True,
        },
    )
    assert response.status_code == 422


def test_plan_request_rejects_invalid_language():
    response = client.post(
        "/api/plans",
        json={"request": "Prepare Java development", "language": "fr"},
    )
    assert response.status_code == 422


def test_plan_endpoint_does_not_expose_acknowledgement_or_execution_routes():
    plan = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    ).json()["dry_run_plan"]
    plan_id = plan["plan_id"]

    assert client.post(f"/api/plans/{plan_id}/acknowledgement", json={}).status_code == 404
    assert client.post("/api/execute", json={"plan_id": plan_id}).status_code == 404


def test_java_development_task_cannot_create_or_refine_a_legacy_install_plan():
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    )
    assert initial.status_code == 200
    body = initial.json()
    assert body["dry_run_plan"] is None
    assert len(body["questions"]) == 2
    assert body["notice"] == "PLAN_REVIEW_ONLY_NO_EXECUTION"

    refined = client.post(
        f"/api/plans/{'0' * 32}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "JDK 21 LTS",
            "language": "th",
        },
    )
    assert refined.status_code == 404


def test_plan_request_rejects_an_arbitrary_unknown_field():
    response = client.post(
        "/api/plans",
        json={
            "request": "Install Google Chrome",
            "language": "en",
            "client_trace": "untrusted-extra",
        },
    )

    assert response.status_code == 422


def test_plan_refinement_request_rejects_an_arbitrary_unknown_field():
    initial = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    )
    assert initial.status_code == 200
    plan_id = initial.json()["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/refine",
        json={
            "request": "Uninstall Google Chrome",
            "clarification": "Remove the selected application",
            "language": "en",
            "client_trace": "untrusted-extra",
        },
    )

    assert response.status_code == 422


def test_plan_creation_never_calls_dry_run_tool(monkeypatch):
    from agent_backend import plan_api

    def forbidden(_request):
        raise AssertionError("dry run must wait for explicit approval")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    response = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["tool_result"] is None
    assert response.json()["approved"] is False


def test_approval_fails_closed_without_google_and_authenticator_configuration(monkeypatch):
    from agent_backend import plan_api
    from agent_backend.tools import ToolResult

    calls = []

    def dry_run(request):
        calls.append(request)
        return ToolResult(
            tool_id=request.tool_id,
            target=request.target,
            status="dry_run",
            summary="Mock dry run",
        )

    monkeypatch.setattr(plan_api, "execute_tool", dry_run)
    created = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    ).json()
    plan_id = created["dry_run_plan"]["plan_id"]

    first = client.post(f"/api/plans/{plan_id}/approve", json={})
    second = client.post(f"/api/plans/{plan_id}/approve", json={})

    assert first.status_code == 503
    assert second.status_code == 503
    assert calls == []



def test_approval_rejects_client_supplied_authority_or_action_fields(monkeypatch):
    from agent_backend import plan_api

    calls = []

    def forbidden(request):
        calls.append(request)
        raise AssertionError("untrusted approval payload must not dispatch")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    created = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    ).json()
    plan_id = created["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/approve",
        json={"approved": True, "tool_id": "software.remove", "target": "untrusted"},
    )
    assert response.status_code == 422
    assert calls == []


def test_explicit_software_install_does_not_create_a_legacy_dry_run_plan(monkeypatch):
    from agent_backend import plan_api

    calls = []

    def forbidden(request):
        calls.append(request)
        raise AssertionError("software.install must use the real WinGet proposal path")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    created = client.post(
        "/api/plans",
        json={"request": "Install Google Chrome", "language": "en"},
    )

    assert created.status_code == 200
    body = created.json()
    assert body["interpretation"]["category"] == "software_install"
    assert body["dry_run_plan"] is None
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert body["notice"] == "PLAN_REVIEW_ONLY_NO_EXECUTION"
    assert calls == []


def test_stale_software_install_plan_is_rejected_by_legacy_approval_route():
    from types import SimpleNamespace

    from fastapi import HTTPException

    from agent_backend.plan_api import PlanApprovalRequest, _plan_store, approve_plan_review
    from agent_backend.plans import ProgramPlan

    legacy_plan = _plan_store.create(
        "software.install",
        (
            ProgramPlan(
                order=1,
                program="Google Chrome",
                version="Stable",
                purpose="Browser",
                reason="Legacy plan fixture",
                source="Not checked",
                impact="Not checked",
                status="PLANNED",
            ),
        ),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace()),
        state=SimpleNamespace(),
    )

    with pytest.raises(HTTPException) as error:
        approve_plan_review(legacy_plan.plan_id, PlanApprovalRequest(), request)

    assert error.value.status_code == 409
    assert "dedicated exact-action approval route" in error.value.detail



def test_java_development_clarification_does_not_mint_install_preview(monkeypatch):
    from agent_backend import plan_api

    def forbidden(_request):
        raise AssertionError("Java development planning must not reach install preview dispatch")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    created = client.post(
        "/api/plans",
        json={"request": "Prepare Java development", "language": "en"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["dry_run_plan"] is None
    assert len(body["questions"]) == 2
    assert body["notice"] == "PLAN_REVIEW_ONLY_NO_EXECUTION"



def test_plan_creation_does_not_depend_on_a_second_gemini_call(monkeypatch):
    from agent_backend import plan_api

    def forbidden(*_args, **_kwargs):
        raise AssertionError("plan creation must use the deterministic backend planner")

    # The chat response already came from Gemini. The plan API must not make
    # another provider call or require Gemini structured-output support.
    monkeypatch.setattr(plan_api, "generate_structured_plan", forbidden, raising=False)
    response = client.post(
        "/api/plans",
        json={"request": "ติดตั้ง Google Chrome", "language": "th"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["interpretation"]["category"] == "software_install"
    assert body["interpretation"]["target"] == "Google Chrome"
    assert body["dry_run_plan"] is None
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert body["questions"] == []
    assert body["notice"] == "PLAN_REVIEW_ONLY_NO_EXECUTION"



def test_plan_creation_records_minimal_in_memory_audit_event():
    from agent_backend.audit import AUDIT_SINK

    AUDIT_SINK.clear()
    response = client.post(
        "/api/plans",
        json={"request": "Uninstall Google Chrome", "language": "en"},
    )

    assert response.status_code == 200
    events = AUDIT_SINK.snapshot()
    assert len(events) == 1
    assert events[0].event_type == "plan.created"
    assert events[0].tool_id == "software.remove"
    assert events[0].outcome == "allowed"
    assert "Google Chrome" not in str(events[0].model_dump())


