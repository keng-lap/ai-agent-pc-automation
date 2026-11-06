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


def test_java_development_request_returns_explicit_dry_run_plan_without_machine_checks():
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
    assert body["tool_result"]["status"] == "dry_run"
    assert "ไม่มีการเปลี่ยนแปลง" in body["tool_result"]["summary"]
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
    assert "ไม่มีการเปลี่ยนแปลง" in body["tool_result"]["summary"]

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
