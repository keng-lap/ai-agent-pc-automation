import httpx2
import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from agent_backend import chat as chat_module
from agent_backend.main import app
from agent_backend.providers import gemini

CONVERSATION_ID = "123e4567-e89b-42d3-a456-426614174000"
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
    chat_module._conversation_store.clear()


def _chat_payload(message="hello", language="en", conversation_id=CONVERSATION_ID):
    return {
        "conversation_id": conversation_id,
        "message": message,
        "language": language,
    }


def test_status_does_not_expose_api_key():
    response = client.get("/api/settings/gemini")
    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "model": "gemini-3.8-flash",
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


def test_gemini_client_explicitly_uses_developer_api(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(gemini.genai, "Client", Client)
    gemini.save_api_key("test-gemini-api-key-123456789")
    gemini._client()
    assert calls == [{"api_key": "test-gemini-api-key-123456789", "vertexai": False}]


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
        "model": "gemini-3.8-flash",
    }
    assert calls == ["tested"]


def test_test_connection_requires_saved_key():
    response = client.post("/api/settings/gemini/test", json={})
    assert response.status_code == 409


def test_chat_uses_gemini_and_returns_plain_reply(monkeypatch):
    calls = []
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "generate_reply", lambda contents: calls.append(contents) or "สวัสดีจาก Gemini")
    response = client.post(
        "/api/chat",
        json=_chat_payload(message="  สวัสดี Gemini  ", language="th"),
    )
    assert response.status_code == 200
    assert response.json() == {
        "reply": "สวัสดีจาก Gemini",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "provider_connected": True,
    }
    assert len(calls) == 1
    assert [(item.role, item.parts[0].text) for item in calls[0]] == [
        ("user", "สวัสดี Gemini"),
    ]




def test_structured_plan_uses_gemini_json_schema(monkeypatch):
    calls = []

    class Response:
        text = '{"goal":"Prepare Java","steps":[{"title":"Review","detail":"Review requirements"}],"questions":[]}'

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return Response()

    class Client:
        models = Models()

    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "_client", lambda: Client())
    class Schema:
        @classmethod
        def model_json_schema(cls):
            return {"type": "OBJECT", "properties": {"goal": {"type": "STRING"}}}

    result = gemini.generate_structured_plan("Create a plan", Schema)

    assert result == Response.text
    assert calls[0]["model"] == "gemini-3.8-flash"
    assert calls[0]["contents"] == "Create a plan"
    assert calls[0]["config"].response_mime_type == "application/json"
    assert calls[0]["config"].response_json_schema == Schema.model_json_schema()


def test_chat_system_instruction_is_supplied_on_every_reply(monkeypatch):
    calls = []

    class Response:
        text = "answer"

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return Response()

    class Client:
        models = Models()

    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "_client", lambda: Client())

    assert gemini.generate_reply("first message") == "answer"
    assert gemini.generate_reply("second message") == "answer"

    assert len(calls) == 2
    for call in calls:
        assert call["model"] == "gemini-3.8-flash"
        assert call["config"].system_instruction == gemini.CHAT_SYSTEM_INSTRUCTION
        assert (
            "Do not ask follow-up questions for optional preferences"
            in call["config"].system_instruction
        )
        assert "DRY RUN" in call["config"].system_instruction


def test_structured_plan_does_not_receive_chat_system_instruction(monkeypatch):
    calls = []

    class Response:
        text = '{"goal":"Prepare Java","steps":[{"title":"Review","detail":"Review requirements"}],"questions":[]}'

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return Response()

    class Client:
        models = Models()

    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "_client", lambda: Client())

    class Schema:
        @classmethod
        def model_json_schema(cls):
            return {"type": "OBJECT", "properties": {"goal": {"type": "STRING"}}}

    assert gemini.generate_structured_plan("Create a plan", Schema) == Response.text
    assert calls[0]["config"].system_instruction is None
    assert calls[0]["config"].response_mime_type == "application/json"


def test_chat_requires_gemini_configuration():
    response = client.post(
        "/api/chat",
        json=_chat_payload(),
    )
    assert response.status_code == 409


def test_upstream_error_is_not_exposed(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")

    def fail(_message):
        raise RuntimeError("sensitive upstream detail")

    monkeypatch.setattr(gemini, "generate_reply", fail)
    response = client.post(
        "/api/chat",
        json=_chat_payload(),
    )
    assert response.status_code == 502
    assert "sensitive upstream detail" not in response.text
    assert response.json() == {
        "detail": {
            "code": "unknown",
            "error_type": "RuntimeError",
            "stage": "provider",
        }
    }


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx2.TimeoutException("sensitive transport detail"), "request_timeout"),
        (httpx2.ConnectError("sensitive transport detail"), "network_error"),
        (errors.UnknownApiResponseError("sensitive response detail"), "invalid_response"),
    ],
)
def test_transport_errors_return_safe_categories(monkeypatch, exception, code):
    class FailingModels:
        def generate_content(self, **_kwargs):
            raise exception

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr(gemini, "_client", lambda: FailingClient())
    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini.generate_reply("hello")
    assert raised.value.code == code
    assert "sensitive" not in str(raised.value)


def test_missing_google_cloud_token_is_classified(monkeypatch):
    class FailingModels:
        def generate_content(self, **_kwargs):
            raise RuntimeError("Could not resolve API token from the environment")

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr(gemini, "_client", lambda: FailingClient())
    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini.generate_reply("hello")
    assert raised.value.code == "google_cloud_auth_missing"
    assert raised.value.error_type is None


def test_unclassified_sdk_runtime_error_exposes_no_message(monkeypatch):
    class FailingModels:
        def generate_content(self, **_kwargs):
            raise RuntimeError("sensitive runtime detail")

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr(gemini, "_client", lambda: FailingClient())
    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini.generate_reply("hello")
    assert raised.value.code == "sdk_runtime_error"
    assert raised.value.error_type == "RuntimeError"
    assert "sensitive runtime detail" not in str(raised.value)


def test_sdk_runtime_error_includes_only_sanitized_trace(monkeypatch):
    class FailingModels:
        def generate_content(self, **_kwargs):
            raise RuntimeError("sensitive runtime detail")

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr(gemini, "_client", lambda: FailingClient())
    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini.generate_reply("hello")
    assert raised.value.stage == "provider_request"
    assert raised.value.trace == []


def test_empty_provider_reply_has_safe_category():
    class EmptyResponse:
        text = None

    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini._response_text(EmptyResponse())
    assert raised.value.code == "empty_response"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (403, "key_or_access"),
        (404, "model_unavailable"),
        (429, "quota_exceeded"),
        (503, "provider_unavailable"),
        (400, "request_rejected"),
    ],
)
def test_gemini_api_errors_return_safe_categories(monkeypatch, status, code):
    gemini.save_api_key("test-gemini-api-key-123456789")

    class FailingModels:
        def generate_content(self, **_kwargs):
            raise errors.ClientError(
                status,
                {"error": {"message": "sensitive upstream detail", "status": "FAILED"}},
            )

    class FailingClient:
        models = FailingModels()

    monkeypatch.setattr(gemini, "_client", lambda: FailingClient())
    with pytest.raises(gemini.GeminiProviderError) as raised:
        gemini.generate_reply("hello")
    assert raised.value.code == code
    assert "sensitive upstream detail" not in str(raised.value)


def test_connection_error_returns_safe_category(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "test_connection",
        lambda: (_ for _ in ()).throw(gemini.GeminiProviderError("quota_exceeded")),
    )
    response = client.post("/api/settings/gemini/test", json={})
    assert response.status_code == 502
    assert response.json() == {"detail": {"code": "quota_exceeded"}}


def test_connection_error_returns_safe_stage_and_trace(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "test_connection",
        lambda: (_ for _ in ()).throw(
            gemini.GeminiProviderError(
                "sdk_runtime_error",
                "RuntimeError",
                "provider_request",
                ["_api_client.request"],
            )
        ),
    )
    response = client.post("/api/settings/gemini/test", json={})
    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "code": "sdk_runtime_error",
            "error_type": "RuntimeError",
            "stage": "provider_request",
            "trace": "_api_client.request",
        }
    }


def test_invalid_chat_payload_is_rejected():
    response = client.post(
        "/api/chat",
        json={**_chat_payload(), "language": "fr"},
    )
    assert response.status_code == 422


def test_get_chat_returns_method_not_allowed():
    response = client.get("/api/chat")
    assert response.status_code == 405


def test_chat_sends_prior_successful_pairs_to_gemini(monkeypatch):
    calls = []
    gemini.save_api_key("test-gemini-api-key-123456789")

    def reply(contents):
        calls.append([(item.role, item.parts[0].text) for item in contents])
        return f"answer {len(calls)}"

    monkeypatch.setattr(gemini, "generate_reply", reply)
    for message in ("first question", "second question"):
        response = client.post("/api/chat", json=_chat_payload(message))
        assert response.status_code == 200

    assert calls == [
        [("user", "first question")],
        [
            ("user", "first question"),
            ("model", "answer 1"),
            ("user", "second question"),
        ],
    ]
    history = client.get(f"/api/chat/{CONVERSATION_ID}")
    assert history.status_code == 200
    assert history.json()["messages"] == [
        {"role": "user", "text": "first question"},
        {"role": "assistant", "text": "answer 1"},
        {"role": "user", "text": "second question"},
        {"role": "assistant", "text": "answer 2"},
    ]


def test_conversation_context_is_isolated(monkeypatch):
    calls = []
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "generate_reply",
        lambda contents: calls.append(contents) or "answer",
    )
    other_conversation_id = "123e4567-e89b-42d3-a456-426614174001"
    assert client.post(
        "/api/chat", json=_chat_payload("private one")
    ).status_code == 200
    assert client.post(
        "/api/chat",
        json=_chat_payload("separate conversation", conversation_id=other_conversation_id),
    ).status_code == 200
    assert [item.parts[0].text for item in calls[1]] == ["separate conversation"]


def test_chat_keeps_only_the_ten_most_recent_pairs(monkeypatch):
    calls = []
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "generate_reply",
        lambda contents: calls.append(contents) or f"answer {len(calls)}",
    )
    for index in range(11):
        response = client.post(
            "/api/chat",
            json=_chat_payload(f"question {index}"),
        )
        assert response.status_code == 200

    assert len(calls[-1]) == 21
    assert calls[-1][0].parts[0].text == "question 0"
    assert calls[-1][-1].parts[0].text == "question 10"
    history = client.get(f"/api/chat/{CONVERSATION_ID}").json()["messages"]
    assert len(history) == 20
    assert history[0] == {"role": "user", "text": "question 1"}
    assert history[-2] == {"role": "user", "text": "question 10"}


def test_failed_reply_is_not_added_to_conversation(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(
        gemini,
        "generate_reply",
        lambda contents: (_ for _ in ()).throw(gemini.GeminiProviderError("quota_exceeded")),
    )
    response = client.post("/api/chat", json=_chat_payload("failed"))
    assert response.status_code == 502
    assert client.get(f"/api/chat/{CONVERSATION_ID}").json() == {"messages": []}


def test_delete_clears_conversation_and_is_idempotent(monkeypatch):
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "generate_reply", lambda _contents: "answer")
    assert client.post("/api/chat", json=_chat_payload()).status_code == 200

    response = client.request("DELETE", f"/api/chat/{CONVERSATION_ID}", json={})
    assert response.status_code == 204
    assert client.get(f"/api/chat/{CONVERSATION_ID}").status_code == 404
    assert client.request("DELETE", f"/api/chat/{CONVERSATION_ID}", json={}).status_code == 204


def test_chat_sessions_are_capped(monkeypatch):
    monkeypatch.setattr(chat_module, "MAX_CONVERSATIONS", 2)
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "generate_reply", lambda _contents: "answer")
    ids = [
        "123e4567-e89b-42d3-a456-426614174001",
        "123e4567-e89b-42d3-a456-426614174002",
        "123e4567-e89b-42d3-a456-426614174003",
    ]
    for conversation_id in ids:
        assert client.post(
            "/api/chat",
            json=_chat_payload(conversation_id=conversation_id),
        ).status_code == 200
    assert client.get(f"/api/chat/{ids[0]}").status_code == 404
    assert client.get(f"/api/chat/{ids[1]}").status_code == 200
    assert client.get(f"/api/chat/{ids[2]}").status_code == 200


def test_idle_conversation_expires(monkeypatch):
    monkeypatch.setattr(chat_module, "CONVERSATION_TTL_SECONDS", 0)
    gemini.save_api_key("test-gemini-api-key-123456789")
    monkeypatch.setattr(gemini, "generate_reply", lambda _contents: "answer")
    assert client.post("/api/chat", json=_chat_payload()).status_code == 200
    assert client.get(f"/api/chat/{CONVERSATION_ID}").status_code == 404
