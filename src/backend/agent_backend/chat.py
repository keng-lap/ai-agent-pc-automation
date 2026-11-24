"""Gemini chat and provider settings endpoints for the local MVP."""

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_backend.conversation_contract import UniversalConversationResponse
from agent_backend.providers import gemini, grok
from agent_backend.runtime_diagnostics import emit_event, emit_exception

router = APIRouter()
_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
MAX_CONTEXT_PAIRS = 10
MAX_CONVERSATIONS = 128
CONVERSATION_TTL_SECONDS = 60 * 60


@dataclass
class _Conversation:
    turns: list[tuple[str, str]] = field(default_factory=list)
    last_access: float = field(default_factory=time.monotonic)
    lock: RLock = field(default_factory=RLock, repr=False)


class _ConversationStore:
    def __init__(self) -> None:
        self._conversations: OrderedDict[UUID, _Conversation] = OrderedDict()
        self._lock = RLock()

    def _remove_expired(self) -> None:
        now = time.monotonic()
        expired = [
            conversation_id
            for conversation_id, conversation in self._conversations.items()
            if now - conversation.last_access >= CONVERSATION_TTL_SECONDS
        ]
        for conversation_id in expired:
            del self._conversations[conversation_id]

    def get(self, conversation_id: UUID) -> _Conversation | None:
        with self._lock:
            self._remove_expired()
            conversation = self._conversations.get(conversation_id)
            if conversation is not None:
                conversation.last_access = time.monotonic()
                self._conversations.move_to_end(conversation_id)
            return conversation

    def get_or_create(self, conversation_id: UUID) -> _Conversation:
        with self._lock:
            self._remove_expired()
            conversation = self._conversations.get(conversation_id)
            if conversation is not None:
                conversation.last_access = time.monotonic()
                self._conversations.move_to_end(conversation_id)
                return conversation

            while len(self._conversations) >= MAX_CONVERSATIONS:
                self._conversations.popitem(last=False)
            conversation = _Conversation()
            self._conversations[conversation_id] = conversation
            return conversation

    def delete(self, conversation_id: UUID) -> None:
        with self._lock:
            self._remove_expired()
            self._conversations.pop(conversation_id, None)

    def clear(self) -> None:
        with self._lock:
            self._conversations.clear()


_conversation_store = _ConversationStore()
_active_provider = "gemini"


def _provider_error_detail(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (gemini.GeminiProviderError, grok.GrokProviderError)):
        detail = {"code": exc.code}
        if exc.error_type:
            detail["error_type"] = exc.error_type
        if exc.stage:
            detail["stage"] = exc.stage
        if exc.trace:
            detail["trace"] = ",".join(exc.trace)
        return detail

    error_type = type(exc).__name__
    if not _ERROR_TYPE_PATTERN.fullmatch(error_type):
        error_type = "Exception"
    logging.getLogger(__name__).warning("AI provider request failed (%s)", error_type)
    return {"code": "unknown", "error_type": error_type, "stage": "provider"}


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    conversation_id: UUID = Field(strict=False)
    message: str
    language: Literal["th", "en"]

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 2000:
            raise ValueError("message length must be between 1 and 2000")
        return value


class GeminiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    api_key: str | None = None
    model: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not 20 <= len(value) <= 512:
            raise ValueError("API key length is invalid")
        return value


@router.get("/api/settings/gemini")
def gemini_status() -> dict[str, object]:
    return {
        "configured": gemini.is_configured(),
        "model": gemini.get_model_name(),
        "models": list(gemini.SUPPORTED_MODELS),
    }


@router.put("/api/settings/gemini")
def save_gemini_key(payload: GeminiKeyRequest) -> dict[str, object]:
    if payload.api_key is None and payload.model is None:
        raise HTTPException(status_code=422, detail="Provide a Gemini API key or model.")
    try:
        selected_model = gemini.validate_model_name(payload.model or gemini.get_model_name())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported Gemini model") from exc
    if not gemini.consume_successful_test(selected_model, payload.api_key):
        raise HTTPException(
            status_code=409,
            detail="Test the selected Gemini model and API key successfully before saving.",
        )
    if payload.api_key is not None:
        gemini.save_api_key(payload.api_key)
    if payload.model is not None:
        gemini.save_model_name(selected_model)
    return {
        "configured": True,
        "model": gemini.get_model_name(),
        "models": list(gemini.SUPPORTED_MODELS),
    }


class GeminiTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model: str | None = None
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_optional_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not 20 <= len(value) <= 512:
            raise ValueError("API key length is invalid")
        return value


@router.post("/api/settings/gemini/test")
def test_gemini_connection(payload: GeminiTestRequest, request: Request) -> dict[str, object]:
    try:
        selected_model = gemini.validate_model_name(payload.model or gemini.get_model_name())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported Gemini model") from exc
    gemini.clear_successful_test()
    if not payload.api_key and not gemini.is_configured():
        raise HTTPException(status_code=409, detail="Gemini API key is not configured.")
    started = time.perf_counter()
    correlation = getattr(request.state, "correlation_id", "unknown")
    emit_event(
        event_code="GEMINI_CONNECTION_TEST_STARTED",
        component="gemini",
        stage="provider_connection",
        correlation=correlation,
    )
    try:
        gemini.test_connection(model=selected_model, api_key=payload.api_key)
        gemini.record_successful_test(selected_model, payload.api_key)
    except gemini.GeminiProviderError as exc:
        emit_exception(
            event_code="GEMINI_CONNECTION_TEST_FAILED",
            component="gemini",
            stage="provider_connection",
            correlation=correlation,
            error=exc,
            fields={"provider_error_code": exc.code},
        )
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    except Exception as exc:  # noqa: BLE001 - sanitize all SDK and transport errors
        emit_exception(
            event_code="GEMINI_CONNECTION_TEST_FAILED",
            component="gemini",
            stage="provider_connection",
            correlation=correlation,
            error=exc,
        )
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    emit_event(
        event_code="GEMINI_CONNECTION_TEST_SUCCEEDED",
        component="gemini",
        stage="provider_connection",
        correlation=correlation,
        fields={"duration_ms": round((time.perf_counter() - started) * 1000, 2)},
    )
    return {"connected": True, "model": selected_model}




class GrokKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    api_key: str | None = None
    model: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not 20 <= len(value) <= 512:
            raise ValueError("API key length is invalid")
        return value


class GrokTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str | None = None
    api_key: str | None = None

    @field_validator("api_key")
    @classmethod
    def validate_optional_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not 20 <= len(value) <= 512:
            raise ValueError("API key length is invalid")
        return value


class ProviderSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["gemini", "grok"]


@router.get("/api/settings/grok")
def grok_status() -> dict[str, object]:
    return {"configured": grok.is_configured(), "model": grok.get_model_name(),
            "models": list(grok.SUPPORTED_MODELS)}


@router.post("/api/settings/grok/test")
def test_grok_connection(payload: GrokTestRequest, request: Request) -> dict[str, object]:
    try:
        selected_model = grok.validate_model_name(payload.model or grok.get_model_name())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported Grok model") from exc
    grok.clear_successful_test()
    if not payload.api_key and not grok.is_configured():
        raise HTTPException(status_code=409, detail="Grok API key is not configured.")
    started = time.perf_counter()
    correlation = getattr(request.state, "correlation_id", "unknown")
    emit_event(event_code="GROK_CONNECTION_TEST_STARTED", component="grok",
               stage="provider_connection", correlation=correlation)
    try:
        grok.test_connection(model=selected_model, api_key=payload.api_key)
        grok.record_successful_test(selected_model, payload.api_key)
    except grok.GrokProviderError as exc:
        emit_exception(event_code="GROK_CONNECTION_TEST_FAILED", component="grok",
                       stage="provider_connection", correlation=correlation, error=exc,
                       fields={"provider_error_code": exc.code})
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    except Exception as exc:  # noqa: BLE001 - sanitize SDK and transport errors
        emit_exception(event_code="GROK_CONNECTION_TEST_FAILED", component="grok",
                       stage="provider_connection", correlation=correlation, error=exc)
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    emit_event(event_code="GROK_CONNECTION_TEST_SUCCEEDED", component="grok",
               stage="provider_connection", correlation=correlation,
               fields={"duration_ms": round((time.perf_counter() - started) * 1000, 2)})
    return {"connected": True, "model": selected_model}


@router.put("/api/settings/grok")
def save_grok_key(payload: GrokKeyRequest) -> dict[str, object]:
    if payload.api_key is None and payload.model is None:
        raise HTTPException(status_code=422, detail="Provide a Grok API key or model.")
    try:
        selected_model = grok.validate_model_name(payload.model or grok.get_model_name())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported Grok model") from exc
    if not grok.consume_successful_test(selected_model, payload.api_key):
        raise HTTPException(status_code=409,
            detail="Test the selected Grok model and API key successfully before saving.")
    if payload.api_key is not None:
        grok.save_api_key(payload.api_key)
    if payload.model is not None:
        grok.save_model_name(selected_model)
    return {"configured": True, "model": grok.get_model_name(),
            "models": list(grok.SUPPORTED_MODELS)}


@router.get("/api/settings/provider")
def provider_status() -> dict[str, object]:
    return {"active": _active_provider, "gemini_configured": gemini.is_configured(),
            "grok_configured": grok.is_configured(), "gemini_model": gemini.get_model_name(),
            "grok_model": grok.get_model_name()}


@router.put("/api/settings/provider")
def select_provider(payload: ProviderSelectionRequest) -> dict[str, object]:
    global _active_provider
    configured = gemini.is_configured() if payload.provider == "gemini" else grok.is_configured()
    if not configured:
        raise HTTPException(status_code=409,
            detail=f"{payload.provider.title()} API key is not configured and tested.")
    _active_provider = payload.provider
    return provider_status()


def _provider_messages(contents: list[types.Content]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": gemini.UNIVERSAL_RESPONSE_SYSTEM_INSTRUCTION}
    ]
    for item in contents:
        role = "assistant" if item.role == "model" else "user"
        content = "".join(part.text for part in (item.parts or []) if isinstance(part.text, str))
        messages.append({"role": role, "content": content})
    return messages


def _generate_universal_response(provider: str, contents: list[types.Content],
                                 response_schema: type) -> str:
    if provider == "grok":
        return grok.generate_universal_response(_provider_messages(contents), response_schema)
    return gemini.generate_universal_response(contents, response_schema)


def _provider_configured(provider: str) -> bool:
    return grok.is_configured() if provider == "grok" else gemini.is_configured()


def _provider_model(provider: str) -> str:
    return grok.get_model_name() if provider == "grok" else gemini.get_model_name()


@router.post("/api/chat")
def chat(payload: ChatRequest, request: Request) -> dict[str, object]:
    provider = _active_provider
    if not _provider_configured(provider):
        raise HTTPException(status_code=409, detail=f"Configure {provider.title()} API key first.")
    started = time.perf_counter()
    correlation = getattr(request.state, "correlation_id", "unknown")
    emit_event(
        event_code=f"{provider.upper()}_REQUEST_STARTED",
        component=provider,
        stage="provider_generation",
        correlation=correlation,
        fields={"model": _provider_model(provider)},
    )
    conversation = _conversation_store.get_or_create(payload.conversation_id)
    with conversation.lock:
        contents: list[types.Content] = []
        for user_message, assistant_message in conversation.turns:
            contents.extend(
                [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=user_message)],
                    ),
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=assistant_message)],
                    ),
                ]
            )
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=payload.message)])
        )
        try:
            raw_response = _generate_universal_response(
                provider, contents, UniversalConversationResponse,
            )
            if len(raw_response) > 16000:
                raise gemini.GeminiProviderError("invalid_response")
            try:
                structured = UniversalConversationResponse.model_validate_json(raw_response)
            except ValidationError:
                emit_event(
                    event_code=f"{provider.upper()}_STRUCTURED_RESPONSE_REPAIR_ATTEMPTED",
                    component=provider,
                    stage="structured_response_validation",
                    correlation=correlation,
                    severity="WARNING",
                )
                # One bounded correction attempt. The malformed output remains untrusted
                # and is never returned as a valid plan or saved into conversation history.
                repair_contents = [
                    *contents,
                    types.Content(role="model", parts=[types.Part.from_text(text=raw_response[:12000])]),
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            text=(
                                "Your previous response did not satisfy the required JSON schema. "
                                "Return one corrected JSON object only, matching the same schema. "
                                "Do not add commentary or extra fields."
                            )
                        )],
                    ),
                ]
                raw_response = _generate_universal_response(
                    provider, repair_contents, UniversalConversationResponse,
                )
                if len(raw_response) > 16000:
                    raise gemini.GeminiProviderError("invalid_response")
                try:
                    structured = UniversalConversationResponse.model_validate_json(raw_response)
                except ValidationError:
                    raise gemini.GeminiProviderError("invalid_response") from None
        except (gemini.GeminiProviderError, grok.GrokProviderError) as exc:
            emit_exception(
                event_code=f"{provider.upper()}_REQUEST_FAILED",
                component=provider,
                stage="provider_generation",
                correlation=correlation,
                error=exc,
                fields={"provider_error_code": exc.code},
            )
            raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
        except Exception as exc:  # noqa: BLE001 - sanitize all SDK and transport errors
            emit_exception(
                event_code=f"{provider.upper()}_REQUEST_FAILED",
                component=provider,
                stage="provider_generation",
                correlation=correlation,
                error=exc,
            )
            raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None

        emit_event(
            event_code=f"{provider.upper()}_RESPONSE_VALIDATED",
            component=provider,
            stage="structured_response_validation",
            correlation=correlation,
            fields={
                "response_bytes": len(raw_response.encode("utf-8")),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        request_id = correlation
        normalized = structured.model_dump(mode="json")
        conversation.turns.append((payload.message, structured.message))
        del conversation.turns[:-MAX_CONTEXT_PAIRS]
        conversation.last_access = time.monotonic()
    return {
        "request_id": request_id,
        "gemini_response": normalized,
        "gemini_raw_json": raw_response,
        "provider": provider,
        "model": _provider_model(provider),
        "provider_connected": True,
    }


@router.get("/api/chat/{conversation_id}")
def get_chat_history(conversation_id: UUID) -> dict[str, list[dict[str, str]]]:
    conversation = _conversation_store.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    with conversation.lock:
        messages = [
            message
            for user_message, assistant_message in conversation.turns
            for message in (
                {"role": "user", "text": user_message},
                {"role": "assistant", "text": assistant_message},
            )
        ]
    return {"messages": messages}


@router.delete("/api/chat/{conversation_id}", status_code=204)
def clear_chat_history(conversation_id: UUID) -> None:
    _conversation_store.delete(conversation_id)
