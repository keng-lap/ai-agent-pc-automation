import pytest
from fastapi.testclient import TestClient

from agent_backend.main import app
from agent_backend.providers import gemini

client = TestClient(
    app,
    base_url="http://127.0.0.1:8000",
    headers={
        "origin": "http://127.0.0.1:4200",
        "x-local-agent-token": "a" * 64,
    },
)


@pytest.fixture(autouse=True)
def clear_provider_key(monkeypatch):
    monkeypatch.setattr(gemini, "_api_key", None)


def test_status_does_not_expose_api_key():
    response = client.get("/api/settings/gemini")
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "model": "gemini-3.1-flash-lite",
    }


def test_save_key_keeps_it_out_of_response(monkeypatch):
    response = client.put(
        "/api/settings/gemini",
        json={"api_key": "test-gemini-api-key-123456789"},
    )
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "api_key" not in response.json()
    assert gemini.is_configured()


@pytest.mark.parametrize("api_key", ["", "too-short", "x" * 513])
def test_invalid_api_key_is_rejected(api_key):
    response = client.put("/api/settings/gemini", json={"api_key": api_key})
    assert response.status_code == 422
    assert not gemini.is_configured()


def test_test_connection_uses_saved_key(monkeypatch):
    calls = []
    monkeypatch.setattr(gemini, "test_connection", lambda: calls.append("tested"))
    gemini.save_api_key("test-gemini-api-key-123456789")
    response = client.post("/api/settings/gemini/test", json={})
    assert response.status_code == 200
    assert response.json() == {
        "connected": True,
        "model": "gemini-3.1-flash-lite",
    }
    assert calls == ["tested"]


def test_test_connection_requires_saved_key():
    response = client.post("/api/settings/gemini/test", json={})
    assert response.status_code == 409


def test_chat_uses_gemini_and_returns_plain_reply(monkeypatch):
    calls = []
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "generate_reply",
        lambda message: calls.append(message) or "สวัสดีจาก Gemini",
    )
    response = client.post(
        "/api/chat",
        json={"message": "  สวัสดี Gemini  ", "language": "th"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "reply": "สวัสดีจาก Gemini",
        "provider": "gemini",
        "model": "gemini-3.1-flash-lite",
        "provider_connected": True,
    }
    assert calls == ["สวัสดี Gemini"]


def test_chat_requires_gemini_configuration():
    response = client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
    )
    assert response.status_code == 409


def test_upstream_error_is_not_exposed(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")

    def fail(_message):
        raise RuntimeError("sensitive upstream detail")

    monkeypatch.setattr(gemini, "generate_reply", fail)
    response = client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
    )
    assert response.status_code == 502
    assert "sensitive upstream detail" not in response.text


def test_invalid_chat_payload_is_rejected():
    response = client.post("/api/chat", json={"message": "hello", "language": "fr"})
    assert response.status_code == 422


def test_get_chat_returns_method_not_allowed():
    response = client.get("/api/chat")
    assert response.status_code == 405
