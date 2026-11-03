"""Gemini chat and provider settings endpoints for the local MVP."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from agent_backend.providers import gemini

router = APIRouter()


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
    except Exception:  # noqa: BLE001 - sanitize all SDK and transport errors
        raise HTTPException(status_code=502, detail="Gemini connection test failed.") from None
    return {"connected": True, "model": gemini.MODEL_NAME}


@router.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, object]:
    if not gemini.is_configured():
        raise HTTPException(status_code=409, detail="Configure Gemini API key first.")
    try:
        reply = gemini.generate_reply(payload.message)
    except Exception:  # noqa: BLE001 - sanitize all SDK and transport errors
        raise HTTPException(status_code=502, detail="Gemini request failed.") from None
    return {
        "reply": reply,
        "provider": "gemini",
        "model": gemini.MODEL_NAME,
        "provider_connected": True,
    }
