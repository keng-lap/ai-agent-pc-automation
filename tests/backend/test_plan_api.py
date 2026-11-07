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


def test_java_development_request_returns_plan_without_running_dry_run():
    response = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request"] == "เตรียมเครื่องพัฒนา Java"
    assert body["interpretation"]["category"] == "development_task"
    assert body["interpretation"]["target"] == "Java"
    assert body["dry_run_plan"]["mode"] == "dry_run"
    assert body["dry_run_plan"]["live_checks_performed"] is False
    assert body["dry_run_plan"]["programs"][0]["program"] == "JDK"
    assert body["dry_run_plan"]["programs"][0]["status"] == "NEEDS_CLARIFICATION"
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert body["questions"] == [
        "ต้องการ JDK เวอร์ชันใด (เช่น 21 LTS)?",
        "ต้องการใช้ IDE ใด หรือให้แนะนำตัวเลือกก่อน?",
    ]
    assert body["notice"] == "DRY_RUN_ONLY_NO_CHANGES_MADE"


def test_plan_can_be_read_by_opaque_id_from_process_store():
    created = client.post(
        "/api/plans",
        json={"request": "Install Google Chrome", "language": "en"},
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
        json={"request": "Install Google Chrome", "language": "en"},
    ).json()["dry_run_plan"]
    plan_id = plan["plan_id"]

    assert client.post(f"/api/plans/{plan_id}/acknowledgement", json={}).status_code == 404
    assert client.post("/api/execute", json={"plan_id": plan_id}).status_code == 404


def test_java_plan_refinement_creates_a_new_immutable_plan_from_explicit_answers():
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    old_plan_id = initial["dry_run_plan"]["plan_id"]

    refined = client.post(
        f"/api/plans/{old_plan_id}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "เอา JDK 21 LTS และ IntelliJ IDEA",
            "language": "th",
        },
    )

    assert refined.status_code == 200
    body = refined.json()
    assert body["refined_from_plan_id"] == old_plan_id
    assert body["clarification"] == "เอา JDK 21 LTS และ IntelliJ IDEA"
    assert body["dry_run_plan"]["plan_id"] != old_plan_id
    assert [item["program"] for item in body["dry_run_plan"]["programs"]] == [
        "JDK",
        "IntelliJ IDEA",
    ]
    assert body["dry_run_plan"]["programs"][0]["version"] == "21 LTS"
    assert body["dry_run_plan"]["programs"][0]["status"] == "PLANNED"
    assert body["questions"] == []
    assert body["dry_run_plan"]["live_checks_performed"] is False
    assert body["tool_result"] is None
    assert body["approved"] is False

    old_plan = client.get(f"/api/plans/{old_plan_id}")
    assert old_plan.status_code == 200
    assert old_plan.json()["programs"][0]["version"] == "ยังไม่ได้ระบุ"


def test_java_refinement_does_not_infer_an_unlisted_version_or_optional_ide():
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    plan_id = initial["dry_run_plan"]["plan_id"]

    refined = client.post(
        f"/api/plans/{plan_id}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "ใช้เวอร์ชันล่าสุดและเลือก IDE ให้เหมาะสม",
            "language": "th",
        },
    )

    assert refined.status_code == 200
    body = refined.json()
    assert body["dry_run_plan"]["programs"][0]["version"] == "ยังไม่ได้ระบุ"
    assert body["dry_run_plan"]["programs"][0]["status"] == "NEEDS_CLARIFICATION"
    assert len(body["dry_run_plan"]["programs"]) == 1
    assert len(body["questions"]) == 2


def test_java_refinement_rejects_a_different_original_request():
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    plan_id = initial["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/refine",
        json={
            "request": "Install Google Chrome",
            "clarification": "JDK 21",
            "language": "th",
        },
    )

    assert response.status_code == 409


def test_java_refinement_rejects_client_supplied_policy_fields():
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    plan_id = initial["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "JDK 21",
            "language": "th",
            "approved": True,
            "execute": True,
        },
    )

    assert response.status_code == 422


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
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    )
    assert initial.status_code == 200
    plan_id = initial.json()["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "JDK 21 LTS",
            "language": "th",
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
        json={"request": "Install Google Chrome", "language": "en"},
    )
    assert response.status_code == 200
    assert response.json()["tool_result"] is None
    assert response.json()["approved"] is False


def test_approval_runs_every_plan_item_once_and_replays_cached_result(monkeypatch):
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
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    refined = client.post(
        f"/api/plans/{initial['dry_run_plan']['plan_id']}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "JDK 21 LTS และ IntelliJ IDEA",
            "language": "th",
        },
    ).json()
    plan_id = refined["dry_run_plan"]["plan_id"]

    first = client.post(f"/api/plans/{plan_id}/approve", json={})
    second = client.post(f"/api/plans/{plan_id}/approve", json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["approved"] is True
    assert first.json()["notice"] == "DRY_RUN_ONLY_NO_CHANGES_MADE"
    assert first.json()["tool_result"]["target"] == "JDK, IntelliJ IDEA"
    assert "จะติดตั้ง JDK" in first.json()["tool_result"]["summary"]
    assert "จะติดตั้ง IntelliJ IDEA" in first.json()["tool_result"]["summary"]
    assert "ไม่มีการเปลี่ยนแปลงใด ๆ กับเครื่อง" in first.json()["tool_result"]["summary"]
    assert [call.target for call in calls] == ["JDK", "IntelliJ IDEA"]
    assert len(calls) == 2



def test_approval_rejects_client_supplied_authority_or_action_fields(monkeypatch):
    from agent_backend import plan_api

    calls = []

    def forbidden(request):
        calls.append(request)
        raise AssertionError("untrusted approval payload must not dispatch")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    initial = client.post(
        "/api/plans",
        json={"request": "เตรียมเครื่องพัฒนา Java", "language": "th"},
    ).json()
    refined = client.post(
        f"/api/plans/{initial['dry_run_plan']['plan_id']}/refine",
        json={
            "request": "เตรียมเครื่องพัฒนา Java",
            "clarification": "JDK 21 LTS",
            "language": "th",
        },
    ).json()
    plan_id = refined["dry_run_plan"]["plan_id"]

    response = client.post(
        f"/api/plans/{plan_id}/approve",
        json={"approved": True, "tool_id": "software.remove", "target": "untrusted"},
    )
    assert response.status_code == 422
    assert calls == []


def test_explicit_software_target_can_be_approved_without_optional_questions(monkeypatch):
    from agent_backend import plan_api
    from agent_backend.tools import ToolResult

    monkeypatch.setattr(
        plan_api,
        "generate_structured_plan",
        lambda _prompt, _schema: (
            '{"goal":"Install Google Chrome","steps":'
            '[{"title":"Review requested software","detail":"Google Chrome"}],'
            '"questions":["Which optional Chrome channel do you prefer?"]}'
        ),
    )
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
        json={"request": "Install Google Chrome", "language": "en"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["questions"] == []
    assert body["dry_run_plan"]["programs"][0]["program"] == "Google Chrome"
    assert body["dry_run_plan"]["programs"][0]["status"] == "PLANNED"
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert calls == []

    plan_id = body["dry_run_plan"]["plan_id"]
    approved = client.post(f"/api/plans/{plan_id}/approve", json={})
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert approved.json()["tool_result"]["target"] == "Google Chrome"
    assert len(calls) == 1


def test_approval_rejects_plan_that_needs_clarification(monkeypatch):
    from agent_backend import plan_api

    def forbidden(_request):
        raise AssertionError("ineligible plan must not reach dry-run tool")

    monkeypatch.setattr(plan_api, "execute_tool", forbidden)
    created = client.post(
        "/api/plans",
        json={"request": "Prepare Java development", "language": "en"},
    ).json()
    plan_id = created["dry_run_plan"]["plan_id"]
    response = client.post(f"/api/plans/{plan_id}/approve", json={})
    assert response.status_code == 409



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
    assert body["dry_run_plan"]["programs"][0]["program"] == "Google Chrome"
    assert body["dry_run_plan"]["programs"][0]["status"] == "PLANNED"
    assert body["tool_result"] is None
    assert body["approved"] is False
    assert body["questions"] == []
