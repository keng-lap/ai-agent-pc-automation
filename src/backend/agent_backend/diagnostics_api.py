"""Authenticated runtime diagnostics controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from .auth_api import require_session
from .runtime_diagnostics import is_enabled, set_enabled

router = APIRouter(
    prefix="/api/diagnostics",
    tags=["diagnostics"],
    dependencies=[Depends(require_session)],
)


class DiagnosticsModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool


@router.get("")
def get_diagnostics_mode() -> dict[str, bool]:
    return {"enabled": is_enabled()}


@router.put("")
def update_diagnostics_mode(payload: DiagnosticsModeRequest) -> dict[str, bool]:
    enabled = set_enabled(payload.enabled)
    return {"enabled": enabled}
