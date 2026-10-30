import asyncio
import json
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest
from agent_backend.config import ConfigError, load_settings
from agent_backend.main import app, create_app
from agent_backend.security import MAX_REQUEST_BYTES, LocalWebSecurityMiddleware
from fastapi.testclient import TestClient

BASE_URL = "http://127.0.0.1:8000"
GOOD_ORIGIN = "http://127.0.0.1:4200"
GOOD_HEADERS = {"origin": GOOD_ORIGIN, "x-local-agent-token": "a" * 64}
client = TestClient(app, base_url=BASE_URL, headers=GOOD_HEADERS)

def test_agent_api_rejects_missing_local_token():
    no_token_client = TestClient(app, base_url=BASE_URL, headers={"origin": GOOD_ORIGIN})
    response = no_token_client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Local Agent authorization required."}


def test_agent_api_rejects_incorrect_local_token():
    bad_token_client = TestClient(
        app,
        base_url=BASE_URL,
        headers={"origin": GOOD_ORIGIN, "x-local-agent-token": "b" * 64},
    )
    response = bad_token_client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Local Agent authorization required."}


def test_agent_api_rejects_duplicate_local_token_headers():
    settings = replace(load_settings(load_env_file=False), local_agent_token="a" * 64)
    middleware = LocalWebSecurityMiddleware(_unexpected_app, settings)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/api/chat",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"origin", GOOD_ORIGIN.encode()),
            (b"content-type", b"application/json"),
            (b"x-local-agent-token", b"a" * 64),
            (b"x-local-agent-token", b"a" * 64),
        ],
    }

    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 401


def test_health_remains_available_without_local_token():
    no_token_client = TestClient(app, base_url=BASE_URL)
    response = no_token_client.get("/health")
    assert response.status_code == 200



@pytest.mark.parametrize(
    "host",
    [
        "evil.com",
        "127.0.0.1.evil.com:8000",
        "prefix127.0.0.1:8000",
        "127.0.0.1:9999",
        "[::1]:9999",
    ],
)
def test_foreign_or_inexact_hosts_are_rejected(host):
    response = client.get("/health", headers={"host": host})
    assert response.status_code == 400
    assert response.json() == {"detail": "Host not allowed."}


@pytest.mark.parametrize("host", ["", "localhost:8000", "LOCALHOST:8000", "[::1]:8000"])
def test_empty_host_is_rejected_and_exact_loopback_hosts_are_accepted(host):
    response = client.get("/health", headers={"host": host})
    if host:
        assert response.status_code == 200
    else:
        assert response.status_code == 400


def test_missing_host_is_rejected():
    middleware = LocalWebSecurityMiddleware(_unexpected_app, load_settings(load_env_file=False))
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "GET",
        "path": "/health",
        "headers": [],
    }
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 400


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.com",
        "http://127.0.0.1:9999",
        "https://127.0.0.1:4200",
        "null",
        "http://127.0.0.1.evil.com:4200",
        "http://localhost:4200/",
    ],
)
def test_foreign_or_inexact_origins_are_rejected(origin):
    response = client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
        headers={"origin": origin, "x-local-agent-token": "a" * 64},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Origin not allowed."}


@pytest.mark.parametrize("origin", ["http://127.0.0.1:4200", "http://localhost:4200"])
def test_exact_frontend_origins_are_accepted(origin):
    response = client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
        headers={"origin": origin, "x-local-agent-token": "a" * 64},
    )
    assert response.status_code == 200


def test_missing_origin_is_rejected_for_post_but_allowed_for_health():
    no_origin_client = TestClient(app, base_url=BASE_URL, headers={"x-local-agent-token": "a" * 64})
    post = no_origin_client.post(
        "/api/chat",
        json={"message": "hello", "language": "en"},
    )
    health = no_origin_client.get("/health")
    assert post.status_code == 403
    assert health.status_code == 200


@pytest.mark.parametrize(
    "content_type",
    [None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"],
)
def test_non_json_state_changing_requests_are_rejected(content_type):
    headers = {**GOOD_HEADERS}
    if content_type is not None:
        headers["content-type"] = content_type
    response = client.post(
        "/api/chat", content=b'{"message":"hello","language":"en"}', headers=headers
    )
    assert response.status_code == 415


def test_json_charset_parameter_is_accepted():
    response = client.post(
        "/api/chat",
        content=b'{"message":"hello","language":"en"}',
        headers={**GOOD_HEADERS, "content-type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 200


def test_oversized_body_is_rejected_before_json_parsing():
    response = client.post(
        "/api/chat",
        content=b"x" * (MAX_REQUEST_BYTES + 1),
        headers={**GOOD_HEADERS, "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}


def test_preflight_is_not_handled_and_no_cors_headers_are_sent():
    response = client.options(
        "/api/chat",
        headers={**GOOD_HEADERS, "access-control-request-method": "POST"},
    )
    assert response.status_code == 405
    assert not any(name.lower().startswith("access-control-") for name in response.headers)


def test_foreign_origin_precedes_method_routing():
    response = client.get("/api/chat", headers={"origin": "https://evil.com"})
    assert response.status_code == 403


def test_openapi_get_routes_match_allow_list_and_api_routes_are_post_only():
    paths = app.openapi()["paths"]
    get_routes = {path for path, operations in paths.items() if "get" in operations}
    assert get_routes == {"/health"}
    assert all(
        set(operations) == {"post"}
        for path, operations in paths.items()
        if path.startswith("/api/")
    )


def test_response_has_no_cors_headers_or_cookies():
    response = client.post("/api/chat", json={"message": "hello", "language": "en"})
    assert response.status_code == 200
    assert not any(name.lower().startswith("access-control-") for name in response.headers)
    assert "set-cookie" not in response.headers


def test_docs_endpoints_are_disabled_outside_development():
    settings = replace(load_settings(load_env_file=False), app_env="production")
    production_app = create_app(settings)
    production_client = TestClient(
        production_app,
        base_url=BASE_URL,
        headers=GOOD_HEADERS,
    )
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert production_client.get(path).status_code == 404


@pytest.mark.parametrize("name", ["FRONTEND_PORT", "BACKEND_PORT"])
def test_environment_configuration_rejects_invalid_ports(monkeypatch, name):
    monkeypatch.setenv(name, "invalid")
    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)


@pytest.mark.parametrize("name", ["FRONTEND_PORT", "BACKEND_PORT"])
def test_application_factory_fails_closed_on_invalid_ports(monkeypatch, name):
    monkeypatch.setenv(name, "invalid")
    with pytest.raises(ConfigError):
        create_app()


def test_environment_configuration_rejects_missing_or_malformed_token(monkeypatch):
    for token in ("", "too-short", "G" * 64):
        monkeypatch.setenv("LOCAL_AGENT_TOKEN", token)
        with pytest.raises(ConfigError):
            load_settings(load_env_file=False)


def test_environment_configuration_rejects_non_loopback_bind(monkeypatch):
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)


def test_frontend_dev_server_binds_to_loopback():
    repo_root = Path(__file__).resolve().parents[2]
    angular = json.loads(
        (repo_root / "src/frontend/angular.json").read_text(encoding="utf-8")
    )
    serve = angular["projects"]["frontend"]["architect"]["serve"]["options"]
    assert serve["host"] == "127.0.0.1"


def test_example_configuration_has_no_token_or_secret():
    repo_root = Path(__file__).resolve().parents[2]
    example = (repo_root / ".env.example").read_text(encoding="utf-8").lower()
    assert "local_agent_token=" in example
    assert "local_agent_token=\n" in example
    assert "secret=" not in example
    assert "api_key=" not in example


def test_runtime_dependencies_remain_unchanged():
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads(
        (repo_root / "src/backend/pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["dependencies"] == [
        "fastapi>=0.143",
        "uvicorn>=0.54",
        "python-dotenv>=1.2",
    ]


def test_no_message_content_is_logged(caplog):
    caplog.set_level(0)
    private_text = "private message must never be logged"
    response = client.post(
        "/api/chat", json={"message": private_text, "language": "en"}
    )
    assert response.status_code == 200
    assert private_text not in caplog.text


def test_chunked_body_limit_rejects_body_without_content_length():
    settings = load_settings(load_env_file=False)
    middleware = LocalWebSecurityMiddleware(_unexpected_app, settings)
    events = [
        {"type": "http.request", "body": b"a" * MAX_REQUEST_BYTES, "more_body": True},
        {"type": "http.request", "body": b"b", "more_body": False},
    ]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "method": "POST",
        "path": "/api/chat",
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (b"origin", GOOD_ORIGIN.encode()),
            (b"content-type", b"application/json"),
            (b"x-local-agent-token", b"a" * 64),
        ],
    }
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 413


async def _unexpected_app(scope, receive, send):
    raise AssertionError("oversized body must be rejected before routing")
