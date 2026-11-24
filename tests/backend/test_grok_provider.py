import pytest
import requests

from agent_backend.providers import grok


class _Schema:
    @classmethod
    def model_json_schema(cls):
        return {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        }


class _Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {
            "choices": [{"message": {"content": '{"message":"ok"}'}}]
        }

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def reset_grok(monkeypatch):
    monkeypatch.setattr(grok, "_api_key", None)
    monkeypatch.setattr(grok, "_model_name", grok.MODEL_NAME)
    monkeypatch.setattr(grok, "_tested_configuration", None)


def test_structured_output_uses_xai_schema_and_never_returns_key(monkeypatch):
    calls = []
    api_key = "xai-test-api-key-123456789012"

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return _Response()

    monkeypatch.setattr(grok.requests, "post", post)
    grok.save_api_key(api_key)
    assert grok.generate_universal_response(
        [{"role": "user", "content": "hello"}], _Schema
    ) == '{"message":"ok"}'

    args, kwargs = calls[0]
    assert args == (grok.API_URL,)
    assert kwargs["headers"]["Authorization"] == f"Bearer {api_key}"
    assert kwargs["json"]["model"] == "grok-4.7"
    assert kwargs["json"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "universal_conversation_response",
            "schema": _Schema.model_json_schema(),
            "strict": True,
        },
    }
    assert kwargs["timeout"] == (10, 60)


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "key_or_access"),
        (403, "key_or_access"),
        (404, "model_unavailable"),
        (429, "quota_exceeded"),
        (500, "provider_unavailable"),
        (503, "provider_unavailable"),
        (400, "request_rejected"),
    ],
)
def test_http_errors_are_mapped_to_safe_categories(monkeypatch, status_code, expected):
    monkeypatch.setattr(grok.requests, "post", lambda *_args, **_kwargs: _Response(status_code))
    grok.save_api_key("xai-test-api-key-123456789012")
    with pytest.raises(grok.GrokProviderError) as raised:
        grok.generate_universal_response([], _Schema)
    assert raised.value.code == expected
    assert "secret" not in str(raised.value)


def test_timeout_is_sanitized(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise requests.Timeout("sensitive upstream message")

    monkeypatch.setattr(grok.requests, "post", timeout)
    grok.save_api_key("xai-test-api-key-123456789012")
    with pytest.raises(grok.GrokProviderError) as raised:
        grok.generate_universal_response([], _Schema)
    assert raised.value.code == "request_timeout"
    assert "sensitive" not in str(raised.value)


def test_malformed_response_is_rejected(monkeypatch):
    monkeypatch.setattr(
        grok.requests,
        "post",
        lambda *_args, **_kwargs: _Response(body={"choices": []}),
    )
    grok.save_api_key("xai-test-api-key-123456789012")
    with pytest.raises(grok.GrokProviderError) as raised:
        grok.generate_universal_response([], _Schema)
    assert raised.value.code == "invalid_response"


def test_grok_key_test_must_match_model_and_key():
    api_key = "xai-test-api-key-123456789012"
    grok.record_successful_test("grok-4.7", api_key)
    assert grok.consume_successful_test("grok-4.7", api_key)
    assert not grok.consume_successful_test("grok-4.7", api_key)
