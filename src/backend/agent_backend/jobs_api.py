"""Read-only authenticated Job Status API (P6-602)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth_api import require_session
from .job_lifecycle import JobLifecycleError, JobState
from .job_store import JobStoreUnavailable, SQLiteJobStore
from .oidc import SessionPrincipal

router = APIRouter()


class JobEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sequence: int = Field(ge=1)
    occurred_at: str = Field(min_length=20, max_length=40)
    state: JobState
    level: Literal["INFO", "WARN", "ERROR"]
    message: str = Field(min_length=1, max_length=240)


class JobSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str = Field(min_length=36, max_length=36)
    tool_id: str = Field(min_length=1, max_length=128)
    state: JobState
    created_at: str = Field(min_length=20, max_length=40)
    started_at: str | None = Field(default=None, max_length=40)
    finished_at: str | None = Field(default=None, max_length=40)
    progress_message: str | None = Field(default=None, max_length=160)
    result_code: str | None = Field(default=None, max_length=64)
    reboot_required: bool
    recent_events: list[JobEventResponse] = Field(max_length=20)


class JobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    jobs: list[JobSummaryResponse] = Field(max_length=25)
    checked_at: str


def require_job_owner(
    principal: SessionPrincipal | None = Depends(require_session),
) -> SessionPrincipal:
    """Reject auth-disabled mode even when the shared dependency returns None."""
    if principal is None:
        raise HTTPException(status_code=503, detail="Job status authentication is unavailable.")
    return principal


def _store(request: Request):
    store = getattr(request.app.state, "job_store", None)
    if store is not None:
        return store
    path = getattr(request.app.state, "job_store_path", None)
    lock = getattr(request.app.state, "job_store_lock", None)
    if path is None or lock is None:
        raise HTTPException(status_code=503, detail="Job status storage is unavailable.")
    with lock:
        store = getattr(request.app.state, "job_store", None)
        if store is None:
            try:
                store = SQLiteJobStore(path)
            except JobStoreUnavailable:
                raise HTTPException(
                    status_code=503,
                    detail="Job status storage is unavailable.",
                ) from None
            request.app.state.job_store = store
    return store

@router.get("/api/jobs", response_model=JobListResponse)
def list_jobs(
    request: Request,
    limit: int = Query(default=25, ge=1, le=25),
    principal: SessionPrincipal = Depends(require_job_owner),
) -> JobListResponse:
    try:
        jobs = _store(request).list_for_owner(principal.owner_sub, limit=limit)
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail="Job status storage is unavailable.") from None
    return JobListResponse(
        jobs=jobs,
        checked_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )


@router.get("/api/jobs/{job_id}", response_model=JobSummaryResponse)
def get_job(
    job_id: str,
    request: Request,
    principal: SessionPrincipal = Depends(require_job_owner),
) -> JobSummaryResponse:
    try:
        job = _store(request).get_for_owner(job_id, principal.owner_sub)
    except JobLifecycleError:
        raise HTTPException(status_code=404, detail="Job not found.") from None
    except JobStoreUnavailable:
        raise HTTPException(status_code=503, detail="Job status storage is unavailable.") from None
    return JobSummaryResponse(**job)
