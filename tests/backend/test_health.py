from fastapi.testclient import TestClient

from agent_backend.main import app

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_echoes_valid_request_and_workflow_correlation_ids():
    request_id = "6f1d8e34-0a7b-4f89-9a13-0c8a4d4b8e21"
    workflow_id = "2a4e8f12-6c31-4d80-a58e-9b61f6a42c33"

    response = client.get(
        "/health",
        headers={
            "X-Correlation-ID": request_id,
            "X-Workflow-ID": workflow_id,
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == request_id
    assert response.headers["X-Workflow-ID"] == workflow_id
