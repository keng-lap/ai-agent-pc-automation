"""Minimal Gemini adapter for the local Chat MVP.

The API key is held in process memory only. It is never returned by an API
endpoint, written to disk, or included in logs. Restarting the backend clears it.
"""
from __future__ import annotations

import hashlib
import traceback
from pathlib import PurePath
from threading import RLock

import httpx2
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

MODEL_NAME = "gemini-3.1-flash-lite"
SUPPORTED_MODELS = (
    MODEL_NAME,
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-4-hydrogen",
    "gemini-4-argon",
    "gemini-4-neon",
    "gemini-4-carbon",
)
_model_name = MODEL_NAME
_tested_configuration: tuple[str, str] | None = None


def get_model_name() -> str:
    with _lock:
        return _model_name


def get_api_key() -> str | None:
    """Return the configured key to trusted backend code under the provider lock."""
    with _lock:
        return _api_key


def save_tested_configuration(model: str, api_key: str | None) -> bool:
    """Atomically consume matching test evidence and activate the tested pair."""
    selected_model = validate_model_name(model)
    with _lock:
        key = api_key if api_key is not None else _api_key
        if not key:
            return False
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()
        global _tested_configuration, _api_key, _model_name
        if _tested_configuration != (selected_model, fingerprint):
            return False
        if api_key is not None:
            _api_key = api_key
        _model_name = selected_model
        _tested_configuration = None
        return True


def validate_model_name(model: str) -> str:
    value = model.strip()
    if value not in SUPPORTED_MODELS:
        raise ValueError("Unsupported Gemini model")
    return value


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
            raise GeminiNotConfiguredError("Gemini API key is not configured")
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
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> types.GenerateContentResponse:
    try:
        client = _client(api_key=api_key) if api_key is not None else _client()
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
            model=model or get_model_name(),
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


def test_connection(model: str | None = None, api_key: str | None = None) -> None:
    # Exercise the exact structured-output path used by /api/chat. A plain-text
    # ping can pass while the selected model rejects the chat JSON schema.
    from agent_backend.conversation_contract import UniversalConversationResponse

    raw_response = generate_universal_response(
        "สวัสดี ทดสอบการสนทนาและตอบกลับตามรูปแบบที่กำหนด",
        UniversalConversationResponse,
        model=model,
        api_key=api_key,
    )
    try:
        UniversalConversationResponse.model_validate_json(raw_response)
    except ValidationError:
        raise GeminiProviderError("invalid_response") from None


def generate_reply(contents: str | list[types.Content]) -> str:
    config = types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_INSTRUCTION)
    return _response_text(_generate_content(contents, config=config))

UNIVERSAL_RESPONSE_SYSTEM_INSTRUCTION = """You are the conversational assistant for a local Windows PC automation application.

Always understand and answer the user's natural-language message in the same language. The user may greet you, chat casually, ask questions, request one or many software packages, prepare a development environment, inspect the environment, or request help. Never require the user to use fixed commands or JSON.

Return ONLY one JSON object matching the supplied response schema. Do not use Markdown fences, prose outside JSON, additional keys, or alternate shapes. Every response must include every schema field, including empty arrays and explicit null values. Keep the message field natural and user-friendly.

Intent rules:
- Use conversation.chat for greetings, thanks, casual conversation, and general questions.
- Use system.help for questions about using this application.
- Use software.install for exactly one requested program.
- Use software.install_multiple for two or more requested programs.
- Use environment.prepare for requests to prepare a development or work environment; describe the environment and proposed package list.
- Use environment.inspect when the user asks to check existing tools or environment state. Do not claim you inspected the PC; describe checks the backend would need to perform.
- Use software.remove only when the user explicitly asks to remove one named program.

Data rules:
- Package names, requested versions, purpose, suggested source, and suggested method are proposals only.
- Never invent or supply installer URLs, package IDs, hashes, certificate fingerprints, executable paths, shell commands, PowerShell, scripts, or authorization decisions.
- Do not claim any source, publisher, signature, package, or installed state has been verified.
- For environment preparation, include a useful proposed package list, but do not imply it is approved or installed.
- If essential information is missing, set needs_clarification=true, status="needs_clarification", and provide one concise clarification question. Do not ask for optional preferences when a safe default is available.
- For ordinary chat/help, use empty packages/checks/notes and environment=null.
- The backend independently validates this JSON and independently resolves package identity, source, installer method, trust evidence, and execution policy. Your output never authorizes or executes an action.
""";

def generate_universal_response(
    contents: str | list[types.Content],
    response_schema: type,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> str:
    """Generate schema-constrained JSON under the universal conversation instruction."""
    config = types.GenerateContentConfig(
        system_instruction=UNIVERSAL_RESPONSE_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_json_schema=response_schema.model_json_schema(),
    )
    return _response_text(
        _generate_content(contents, config=config, model=model, api_key=api_key)
    )


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
