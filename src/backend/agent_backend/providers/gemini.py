"""Minimal Gemini adapter for the local Chat MVP.

The API key is held in process memory only. It is never returned by an API
endpoint, written to disk, or included in logs. Restarting the backend clears it.
"""
from __future__ import annotations

import traceback
from pathlib import PurePath
from threading import RLock

import httpx2
from google import genai
from google.genai import errors, types

MODEL_NAME = "gemini-3.1-flash-lite"
_lock = RLock()
_api_key: str | None = None


class GeminiProviderError(RuntimeError):
    """A sanitized, safe-to-display Gemini API failure category."""

    def __init__(
        self,
        code: str,
        error_type: str | None = None,
        stage: str | None = None,
        trace: list[str] | None = None,
    ) -> None:
        self.code = code
        self.error_type = error_type
        self.stage = stage
        self.trace = trace or []
        super().__init__(code)


class GeminiNotConfiguredError(RuntimeError):
    """Raised when a user has not configured a Gemini API key."""


def save_api_key(api_key: str) -> None:
    value = api_key.strip()
    if not 20 <= len(value) <= 512:
        raise ValueError("API key length is invalid")
    with _lock:
        global _api_key
        _api_key = value


def is_configured() -> bool:
    with _lock:
        return _api_key is not None


def _client(api_key: str | None = None) -> genai.Client:
    with _lock:
        key = api_key or _api_key
    if not key:
        raise GeminiNotConfiguredError("Gemini API key is not configured")
    return genai.Client(api_key=key, vertexai=False)


def _safe_sdk_trace(exc: Exception) -> list[str]:
    trace = []
    for frame in traceback.extract_tb(exc.__traceback__):
        parts = PurePath(frame.filename).parts
        if len(parts) >= 3 and parts[-3:-1] == ("google", "genai"):
            trace.append(f"{PurePath(frame.filename).stem}.{frame.name}")
    return trace[-4:]


def _generate_content(
    contents: str | list[types.Content],
    config: types.GenerateContentConfig | None = None,
) -> types.GenerateContentResponse:
    try:
        client = _client()
    except RuntimeError as exc:
        if str(exc) == "Could not resolve API token from the environment":
            raise GeminiProviderError("google_cloud_auth_missing") from None
        raise GeminiProviderError(
            "sdk_runtime_error",
            type(exc).__name__,
            "client_initialization",
            _safe_sdk_trace(exc),
        ) from None

    try:
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )
    except errors.APIError as exc:
        if exc.code in (401, 403):
            code = "key_or_access"
        elif exc.code == 429:
            code = "quota_exceeded"
        elif exc.code == 404:
            code = "model_unavailable"
        elif exc.code >= 500:
            code = "provider_unavailable"
        else:
            code = "request_rejected"
        raise GeminiProviderError(code) from None
    except httpx2.TimeoutException:
        raise GeminiProviderError("request_timeout") from None
    except httpx2.HTTPError:
        raise GeminiProviderError("network_error") from None
    except errors.UnknownApiResponseError:
        raise GeminiProviderError("invalid_response") from None
    except RuntimeError as exc:
        if str(exc) == "Could not resolve API token from the environment":
            raise GeminiProviderError("google_cloud_auth_missing") from None
        raise GeminiProviderError(
            "sdk_runtime_error",
            type(exc).__name__,
            "provider_request",
            _safe_sdk_trace(exc),
        ) from None


def _response_text(response: types.GenerateContentResponse) -> str:
    try:
        reply = (response.text or "").strip()
    except RuntimeError as exc:
        raise GeminiProviderError(
            "sdk_runtime_error",
            type(exc).__name__,
            "response_parsing",
            _safe_sdk_trace(exc),
        ) from None
    if not reply:
        raise GeminiProviderError("empty_response")
    return reply


def test_connection() -> None:
    _response_text(_generate_content("Reply with the single word OK."))


def generate_reply(contents: str | list[types.Content]) -> str:
    return _response_text(_generate_content(contents))



def generate_structured_plan(
    contents: str,
    response_schema: type,
) -> str:
    """Request schema-constrained JSON; callers must validate it before use."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
    )
    return _response_text(_generate_content(contents, config=config))
