"""xAI Grok adapter using xAI's OpenAI-compatible Chat Completions API."""
from __future__ import annotations

import hashlib
from threading import RLock

import requests
from pydantic import ValidationError

MODEL_NAME = "grok-4.7"
SUPPORTED_MODELS = (MODEL_NAME,)
API_URL = "https://api.x.ai/v1/chat/completions"
_lock = RLock()
_api_key: str | None = None
_model_name = MODEL_NAME
_tested_configuration: tuple[str, str] | None = None


class GrokProviderError(RuntimeError):
    """A sanitized, safe-to-display xAI API failure category."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_model_name(model: str) -> str:
    value = model.strip()
    if value not in SUPPORTED_MODELS:
        raise ValueError("Unsupported Grok model")
    return value


def get_model_name() -> str:
    with _lock:
        return _model_name


def is_configured() -> bool:
    with _lock:
        return _api_key is not None


def save_api_key(api_key: str) -> None:
    value = api_key.strip()
    if not 20 <= len(value) <= 512:
        raise ValueError("API key length is invalid")
    with _lock:
        global _api_key
        _api_key = value


def save_model_name(model: str) -> None:
    value = validate_model_name(model)
    with _lock:
        global _model_name
        _model_name = value


def clear_successful_test() -> None:
    with _lock:
        global _tested_configuration
        _tested_configuration = None


def record_successful_test(model: str, api_key: str | None = None) -> None:
    selected_model = validate_model_name(model)
    with _lock:
        key = api_key or _api_key
        if not key:
            raise ValueError("Grok API key is not configured")
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        global _tested_configuration
        _tested_configuration = (selected_model, fingerprint)


def consume_successful_test(model: str, api_key: str | None = None) -> bool:
    selected_model = validate_model_name(model)
    with _lock:
        key = api_key or _api_key
        if not key:
            return False
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        global _tested_configuration
        if _tested_configuration != (selected_model, fingerprint):
            return False
        _tested_configuration = None
        return True


def _selected_key(api_key: str | None = None) -> str:
    with _lock:
        key = api_key or _api_key
    if not key:
        raise GrokProviderError("not_configured")
    return key


def generate_universal_response(
    messages: list[dict[str, str]],
    response_schema: type,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> str:
    selected_model = validate_model_name(model or get_model_name())
    key = _selected_key(api_key)
    payload = {
        "model": selected_model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "universal_conversation_response",
                "schema": response_schema.model_json_schema(),
                "strict": True,
            },
        },
    }
    try:
        response = requests.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(10, 60),
        )
    except requests.Timeout:
        raise GrokProviderError("request_timeout") from None
    except requests.RequestException:
        raise GrokProviderError("network_error") from None

    if response.status_code in (401, 403):
        raise GrokProviderError("key_or_access")
    if response.status_code == 429:
        raise GrokProviderError("quota_exceeded")
    if response.status_code == 404:
        raise GrokProviderError("model_unavailable")
    if response.status_code >= 500:
        raise GrokProviderError("provider_unavailable")
    if response.status_code >= 400:
        raise GrokProviderError("request_rejected")

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise GrokProviderError("invalid_response") from None
    if not isinstance(content, str) or not content.strip():
        raise GrokProviderError("empty_response")
    return content.strip()


def test_connection(model: str | None = None, api_key: str | None = None) -> None:
    from agent_backend.conversation_contract import UniversalConversationResponse

    raw_response = generate_universal_response(
        [
            {
                "role": "system",
                "content": "Return only a JSON object matching the supplied schema. Reply in Thai.",
            },
            {"role": "user", "content": "สวัสดี ทดสอบการตอบกลับตามรูปแบบที่กำหนด"},
        ],
        UniversalConversationResponse,
        model=model,
        api_key=api_key,
    )
    try:
        UniversalConversationResponse.model_validate_json(raw_response)
    except ValidationError:
        raise GrokProviderError("invalid_response") from None
