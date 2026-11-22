"""Backend-owned universal contract for every Gemini conversation turn."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PackageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    purpose: str = Field(max_length=240)
    suggested_source: str = Field(max_length=120)
    suggested_method: str = Field(max_length=120)


class EnvironmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=400)
    development_type: str = Field(max_length=120)
    framework_version: str = Field(max_length=80)


class ConversationData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    packages: list[PackageRequest] = Field(max_length=20)
    environment: EnvironmentRequest | None
    checks: list[str] = Field(max_length=20)
    notes: list[str] = Field(max_length=10)


class UniversalConversationResponse(BaseModel):
    """One stable response envelope; only intent and its data vary."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["1.0"]
    message: str = Field(min_length=1, max_length=4000)
    intent: Literal[
        "conversation.chat",
        "system.help",
        "software.install",
        "software.install_multiple",
        "software.remove",
        "environment.prepare",
        "environment.inspect",
    ]
    status: Literal["completed", "ready", "needs_clarification", "unsupported"]
    data: ConversationData
    needs_clarification: bool
    clarification: str | None

    @model_validator(mode="after")
    def validate_intent_data(self) -> UniversalConversationResponse:
        package_count = len(self.data.packages)
        if self.needs_clarification:
            if self.status != "needs_clarification" or not self.clarification:
                raise ValueError("clarification status requires a clarification message")
        elif self.status == "needs_clarification" or self.clarification is not None:
            raise ValueError("clarification fields are inconsistent")

        if self.intent in {"conversation.chat", "system.help"}:
            if package_count or self.data.environment is not None or self.data.checks:
                raise ValueError("chat/help responses cannot contain action data")
            if self.status not in {"completed", "unsupported", "needs_clarification"}:
                raise ValueError("invalid status for chat/help")
        elif self.intent == "software.install":
            if package_count != 1 or self.data.environment is not None:
                raise ValueError("software.install requires exactly one package")
            if self.status not in {"ready", "needs_clarification", "unsupported"}:
                raise ValueError("invalid status for software.install")
        elif self.intent == "software.install_multiple":
            if package_count < 2 or self.data.environment is not None:
                raise ValueError("software.install_multiple requires at least two packages")
            if self.status not in {"ready", "needs_clarification", "unsupported"}:
                raise ValueError("invalid status for software.install_multiple")
        elif self.intent == "environment.prepare":
            if self.data.environment is None:
                raise ValueError("environment.prepare requires environment details")
            if self.status not in {"ready", "needs_clarification", "unsupported"}:
                raise ValueError("invalid status for environment.prepare")
        elif self.intent == "environment.inspect":
            if not self.data.checks:
                raise ValueError("environment.inspect requires at least one check")
            if self.status not in {"ready", "needs_clarification", "unsupported"}:
                raise ValueError("invalid status for environment.inspect")
        elif self.intent == "software.remove":
            if package_count != 1 or self.data.environment is not None:
                raise ValueError("software.remove requires exactly one named package")
            if self.status not in {"ready", "needs_clarification", "unsupported"}:
                raise ValueError("invalid status for software.remove")
        return self
