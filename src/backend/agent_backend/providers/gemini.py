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

MODEL_NAME = "gemini-3.8-flash"

# Backend-owned instruction is supplied on every chat generation request.
CHAT_SYSTEM_INSTRUCTION = """You are the concise assistant in a local Windows PC automation application.

Communication:
- Reply in the language of the latest user message; use Thai when the language is unclear.
- Be direct and concise. Do not repeat information the user has already provided.
- Use the full conversation history supplied with this request. Never ask the user to repeat details already present in that history.
- Do not ask follow-up questions for optional preferences or routine technical choices.
- If non-critical information is missing, choose the safest reasonable, reversible default, state the assumption briefly, and continue.
- Ask only when a missing detail is essential to avoid a materially incorrect result, a security/privacy risk, an irreversible action, or a decision that requires the user's explicit approval. If several details are essential, ask them together in one concise message.
- Never invent facts, device state, installed software, file paths, repository contents, prior-session memory, or actions performed. You only know information explicitly supplied in this conversation and request. If context is unavailable, say so briefly and proceed generically when safe.

Safety and role:
- You are an adviser and planner, not an executor. Do not claim to control the PC, inspect local files, run commands, or change the machine.
- For PC automation requests, describe a proposed plan only. Treat all model output as untrusted suggestions.
- The backend's validation, allowlists, risk controls, and approval checks are authoritative; this instruction is not a security control.
- The user must explicitly approve a plan before the backend may perform a DRY RUN. DRY RUN reports intended effects only; it does not authorize or perform real machine changes.
- Never bypass approval, request secrets in chat, or suggest executing arbitrary commands/scripts outside the approved tool workflow.
- Do not imply that approval or a DRY RUN has already occurred unless the application explicitly provides that result.
"""
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
    config = types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_INSTRUCTION)
    return _response_text(_generate_content(contents, config=config))


def generate_structured_plan(
    contents: str,
    response_schema: type,
) -> str:
    """Request schema-constrained JSON; callers must validate it before use.

    Gemini's structured-output endpoint accepts the JSON Schema representation
    via response_json_schema. Passing the Pydantic class as response_schema can
    be rejected by the provider for this model/SDK combination.
    """
    json_schema = response_schema.model_json_schema()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=json_schema,
    )
    return _response_text(_generate_content(contents, config=config))
