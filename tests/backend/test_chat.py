import ast
import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_backend import chat as chat_module
from agent_backend.main import app

client = TestClient(
    app,
    base_url="http://127.0.0.1:8000",
    headers={"origin": "http://127.0.0.1:4200"},
)
INVALID_REQUEST = (
    'Invalid request. Send JSON like {"message": "...", "language": "th"} '
    "with 1 to 2000 characters and language th or en."
)
def test_english_request_runs_local_chatgpt_agent_and_dry_run():
    response = client.post(
        "/api/chat", json={"message": "Install Google Chrome", "language": "en"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "chatgpt"
    assert body["provider_connected"] is False
    assert body["plan"]["intent"]["category"] == "software_install"
    assert body["tool_result"]["status"] == "dry_run"
    assert body["tool_result"]["target"] == "Google Chrome"
    assert "ChatGPT selected (local preview" in body["reply"]
    assert "no changes were made" in body["reply"]
    assert response.headers["content-type"].startswith("application/json")


def test_thai_request_returns_localized_plan_and_dry_run():
    response = client.post("/api/chat", json={"message": "สวัสดี", "language": "th"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "chatgpt"
    assert body["provider_connected"] is False
    assert body["plan"]["language"] == "th"
    assert "เลือก ChatGPT แล้ว" in body["reply"]
    assert "ไม่มีเครื่องมือที่อนุญาต" in body["reply"]


def test_message_is_trimmed_before_counting():
    response = client.post("/api/chat", json={"message": "  hi  ", "language": "en"})
    assert response.status_code == 200
    assert response.json()["plan"]["intent"]["goal"] == "hi"


def test_message_length_bounds():
    accepted = client.post("/api/chat", json={"message": "x" * 2000, "language": "en"})
    rejected = client.post("/api/chat", json={"message": "x" * 2001, "language": "en"})
    assert accepted.status_code == 200
    assert accepted.json()["plan"]["intent"]["goal"] == "x" * 2000
    assert rejected.status_code == 422
    assert rejected.json() == {"detail": INVALID_REQUEST}


@pytest.mark.parametrize("message", ["", " \t\n\u2003"])
def test_empty_or_whitespace_message_is_rejected(message):
    response = client.post("/api/chat", json={"message": message, "language": "en"})
    assert response.status_code == 422
    assert response.json() == {"detail": INVALID_REQUEST}


@pytest.mark.parametrize(
    "payload",
    [
        {"language": "en"},
        {"message": "hello"},
        {"message": 1, "language": "en"},
        {"message": "hello", "language": 1},
        {"message": "hello", "language": "fr"},
        {"message": "hello", "language": "en", "provider": "claude"},
        {"message": "hello", "language": "en", "extra": True},
        [],
        None,
    ],
)
def test_invalid_payload_is_rejected_without_details(payload):
    if payload is None:
        response = client.post(
            "/api/chat", content=b"null", headers={"content-type": "application/json"}
        )
    else:
        response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": INVALID_REQUEST}


def test_malformed_json_uses_unified_validation_error():
    response = client.post(
        "/api/chat", content=b'{"message":', headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": INVALID_REQUEST}


def test_agent_response_is_deterministic_and_reply_does_not_echo_message():
    first = client.post("/api/chat", json={"message": "alpha", "language": "en"}).content
    for _ in range(99):
        response = client.post("/api/chat", json={"message": "alpha", "language": "en"})
        assert response.content == first
    other = client.post("/api/chat", json={"message": "bravo", "language": "en"})
    assert other.json()["plan"]["intent"]["goal"] == "bravo"
    assert "alpha" not in response.json()["reply"]


def test_unexpected_exception_returns_generic_error_and_scrubs_message(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(chat_module, "run_agent", fail)
    error_client = TestClient(
        app,
        base_url="http://127.0.0.1:8000",
        headers={"origin": "http://127.0.0.1:4200"},
        raise_server_exceptions=False,
    )
    response = error_client.post("/api/chat", json={"message": "hello", "language": "en"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error."}
    assert b"private internal detail" not in response.content
    assert "private internal detail" not in caplog.text


def test_get_chat_returns_method_not_allowed():
    response = client.get("/api/chat")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


def test_backend_has_no_forbidden_capability_imports():
    package_dir = Path(importlib.import_module("agent_backend").__file__).parent
    forbidden = {
        "subprocess", "ctypes", "winreg", "multiprocessing", "shutil", "socket",
        "urllib", "http.client", "requests", "httpx",
    }

    def imported_names(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield node.module

    for source in package_dir.glob("*.py"):
        names = set(imported_names(ast.parse(source.read_text(encoding="utf-8"))))
        assert not any(
            name == blocked or name.startswith(blocked + ".")
            for name in names
            for blocked in forbidden
        ), f"Forbidden import in {source.name}"
