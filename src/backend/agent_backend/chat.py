"""Deterministic mock chat endpoint for Phase 2 (T-203)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator

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


def make_reply(message: str, language: Literal["th", "en"]) -> str:
    length = len(message)
    if language == "en":
        return (
            f"Message received (length: {length}). The Agent is not implemented yet "
            "(planned for Phase 3)."
        )
    return (
        f"รับข้อความแล้ว (ความยาว: {length} ตัวอักษร) Agent ยังไม่พร้อมใช้งาน "
        "(วางแผนไว้ใน Phase 3)."
    )


@router.post("/api/chat")
def chat(payload: ChatRequest) -> dict[str, str]:
    return {"reply": make_reply(payload.message, payload.language)}
