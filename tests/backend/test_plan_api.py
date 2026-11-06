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
