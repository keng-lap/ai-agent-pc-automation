"""Chat endpoint connected to the local Agent pipeline (T-305)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, field_validator

from agent_backend.agent_core import AgentProvider, AgentResponse, run_agent

router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message: str
    language: Literal["th", "en"]
    provider: AgentProvider = "chatgpt"

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= 2000:
            raise ValueError("message length must be between 1 and 2000")
        return value


@router.post("/api/chat")
def chat(payload: ChatRequest) -> AgentResponse:
    return run_agent(payload.message, payload.language, payload.provider)
