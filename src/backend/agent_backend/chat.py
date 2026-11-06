"""Gemini chat and provider settings endpoints for the local MVP."""

import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from agent_backend.providers import gemini

router = APIRouter()
_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _provider_error_detail(exc: Exception) -> dict[str, str]:
    if isinstance(exc, gemini.GeminiProviderError):
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
    logging.getLogger(__name__).warning("Gemini request failed (%s)", error_type)
    return {"code": "unknown", "error_type": error_type, "stage": "provider"}


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

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

    api_key: str

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        value = value.strip()
        if not 20 <= len(value) <= 512:
            raise ValueError("API key length is invalid")
        return value


@router.get("/api/settings/gemini")
def gemini_status() -> dict[str, object]:
    return {"configured": gemini.is_configured(), "model": gemini.MODEL_NAME}


@router.put("/api/settings/gemini")
def save_gemini_key(payload: GeminiKeyRequest) -> dict[str, object]:
    gemini.save_api_key(payload.api_key)
    return {"configured": True, "model": gemini.MODEL_NAME}


@router.post("/api/settings/gemini/test")
def test_gemini_connection() -> dict[str, object]:
    if not gemini.is_configured():
        raise HTTPException(status_code=409, detail="Gemini API key is not configured.")
    try:
        gemini.test_connection()
    except gemini.GeminiProviderError as exc:
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    except Exception as exc:  # noqa: BLE001 - sanitize all SDK and transport errors
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    return {"connected": True, "model": gemini.MODEL_NAME}


@router.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    if not gemini.is_configured():
        raise HTTPException(status_code=409, detail="Configure Gemini API key first.")
    try:
        reply = gemini.generate_reply(payload.message)
    except gemini.GeminiProviderError as exc:
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    except Exception as exc:  # noqa: BLE001 - sanitize all SDK and transport errors
        raise HTTPException(status_code=502, detail=_provider_error_detail(exc)) from None
    return {
        "reply": reply,
        "provider": "gemini",
        "model": gemini.MODEL_NAME,
        "provider_connected": True,
    }
