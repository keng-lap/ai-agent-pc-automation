from fastapi.testclient import TestClient

from agent_backend.main import app

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
