"""Authenticated runtime diagnostics controls."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from .auth_api import require_session
from .diagnostics_publisher import get_publish_status, start_publish
from .runtime_diagnostics import (
    emit_event,
    export_recent_events,
    is_enabled,
    set_enabled,
    store_available,
)

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
    return {"enabled": is_enabled(), "storage_available": store_available()}


@router.put("")
def update_diagnostics_mode(payload: DiagnosticsModeRequest) -> dict[str, bool]:
    if payload.enabled and not store_available():
        raise HTTPException(status_code=503, detail="Diagnostics storage is unavailable.")
    enabled = set_enabled(payload.enabled)
    if not enabled:
        # Start publishing only after detailed capture has stopped. The daemon thread
        # keeps the OFF response immediate; failures remain retryable from the UI.
        start_publish("diagnostics_disabled")
    return {"enabled": enabled, "storage_available": store_available()}


class BrowserDiagnosticEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    event_code: Literal[
        "BROWSER_UNCAUGHT_ERROR",
        "BROWSER_UNHANDLED_REJECTION",
        "BROWSER_API_FAILURE",
    ]
    status_code: int | None = Field(default=None, ge=100, le=599)
    component: Literal["browser", "api"] = "browser"
    error_type: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    stack: str | None = Field(default=None, max_length=1024, pattern=r"^[0-9:|, -]*$")


@router.post("/browser-events")
def record_browser_event(payload: BrowserDiagnosticEvent, request: Request) -> dict[str, bool]:
    if not is_enabled():
        raise HTTPException(status_code=409, detail="Detailed diagnostics are disabled.")
    emit_event(
        event_code=payload.event_code,
        component=payload.component,
        stage="browser_runtime" if payload.component == "browser" else "api_request",
        correlation=getattr(request.state, "correlation_id", "unknown"),
        severity="ERROR",
        fields={
            key: value
            for key, value in {
                "status_code": payload.status_code,
                "error_type": payload.error_type,
                "stack": payload.stack,
            }.items()
            if value is not None
        },
    )
    return {"recorded": True}


@router.get("/export", response_class=PlainTextResponse)
def export_diagnostics_events(
    limit: int = Query(default=5000, ge=1, le=20000),
) -> PlainTextResponse:
    if not store_available():
        raise HTTPException(status_code=503, detail="Diagnostics storage is unavailable.")
    events = export_recent_events(limit)
    content = "\n".join(
        json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        for event in events
    )
    return PlainTextResponse(
        content=content + ("\n" if content else ""),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/publish")
def publish_diagnostics() -> dict[str, object]:
    """Start an explicit sanitized log publish without blocking the request."""
    return start_publish("manual")


@router.post("/publish/retry")
def retry_diagnostics_publish() -> dict[str, object]:
    """Retry publishing the retained local diagnostics event store."""
    status = get_publish_status()
    if status["status"] == "running":
        return status
    return start_publish("retry")


@router.get("/publish/status")
def diagnostics_publish_status() -> dict[str, object]:
    return get_publish_status()
