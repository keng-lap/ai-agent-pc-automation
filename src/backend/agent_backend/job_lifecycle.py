"""Bounded background-job lifecycle primitives (P6-602).

This module is deliberately storage- and dispatch-agnostic. It contains no
HTTP routes, executable paths, command arguments, or capability handlers.
The in-memory store is for deterministic tests and is NOT production storage.
"""

from __future__ import annotations

import secrets
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class JobLifecycleError(RuntimeError):
    """A job transition or ownership check was rejected."""


class JobState(StrEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REBOOT_REQUIRED = "REBOOT_REQUIRED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


TERMINAL_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.UNKNOWN}
)
_ACTIVE_STATES = frozenset(
    {JobState.STARTING, JobState.RUNNING, JobState.VERIFYING, JobState.CANCEL_REQUESTED}
)
_ALLOWED_TRANSITIONS = {
    JobState.QUEUED: frozenset({JobState.STARTING, JobState.CANCELLED, JobState.FAILED}),
    JobState.STARTING: frozenset(
        {JobState.RUNNING, JobState.CANCEL_REQUESTED, JobState.FAILED, JobState.UNKNOWN}
    ),
    JobState.RUNNING: frozenset(
        {
            JobState.VERIFYING,
            JobState.CANCEL_REQUESTED,
            JobState.FAILED,
            JobState.REBOOT_REQUIRED,
            JobState.UNKNOWN,
        }
    ),
    JobState.VERIFYING: frozenset(
        {JobState.SUCCEEDED, JobState.FAILED, JobState.REBOOT_REQUIRED, JobState.UNKNOWN}
    ),
    JobState.REBOOT_REQUIRED: frozenset({JobState.VERIFYING, JobState.UNKNOWN}),
    JobState.CANCEL_REQUESTED: frozenset({JobState.CANCELLED, JobState.UNKNOWN}),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.UNKNOWN: frozenset(),
}


@dataclass(frozen=True, slots=True)
class WorkerLease:
    worker_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    owner_id: str
    tool_id: str
    action_digest: str
    idempotency_key: str
    state: JobState
    created_at: datetime
    updated_at: datetime
    version: int = 0
    lease: WorkerLease | None = None
    result_code: str | None = None


class InMemoryJobStore:
    """Thread-safe reference store; never use as durable production storage."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    @staticmethod
    def _validate_identity(value: str, field: str, max_length: int = 128) -> None:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > max_length
            or value.strip() != value
            or any(ord(char) < 0x21 for char in value)
        ):
            raise ValueError(f"invalid {field}")

    @staticmethod
    def _validate_digest(value: str) -> None:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise ValueError("action_digest must be a lowercase SHA-256 hex digest")

    @staticmethod
    def _validate_time(value: datetime) -> None:
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")

    def create(
        self,
        *,
        owner_id: str,
        tool_id: str,
        action_digest: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> JobRecord:
        self._validate_identity(owner_id, "owner_id")
        self._validate_identity(tool_id, "tool_id")
        self._validate_identity(idempotency_key, "idempotency_key")
        self._validate_digest(action_digest)
        created_at = now or datetime.now(UTC)
        self._validate_time(created_at)
        key = (owner_id, idempotency_key)
        with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                existing = self._jobs[existing_id]
                if existing.tool_id != tool_id or existing.action_digest != action_digest:
                    raise JobLifecycleError("idempotency key was reused for a different action")
                return existing
            record = JobRecord(
                job_id=str(uuid.uuid4()),
                owner_id=owner_id,
                tool_id=tool_id,
                action_digest=action_digest,
                idempotency_key=idempotency_key,
                state=JobState.QUEUED,
                created_at=created_at,
                updated_at=created_at,
            )
            self._jobs[record.job_id] = record
            self._idempotency[key] = record.job_id
            return record

    def get_for_owner(self, job_id: str, owner_id: str) -> JobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None or not secrets.compare_digest(record.owner_id, owner_id):
                raise JobLifecycleError("job not found")
            return record

    def claim_next(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int = 30,
    ) -> tuple[JobRecord, WorkerLease] | None:
        self._validate_identity(worker_id, "worker_id")
        self._validate_time(now)
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        with self._lock:
            queued = sorted(
                (job for job in self._jobs.values() if job.state is JobState.QUEUED),
                key=lambda job: (job.created_at, job.job_id),
            )
            if not queued:
                return None
            current = queued[0]
            lease = WorkerLease(
                worker_id=worker_id,
                token=secrets.token_urlsafe(32),
                expires_at=now + timedelta(seconds=lease_seconds),
            )
            claimed = replace(
                current,
                state=JobState.STARTING,
                lease=lease,
                updated_at=now,
                version=current.version + 1,
            )
            self._jobs[current.job_id] = claimed
            return claimed, lease

    def transition(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_token: str,
        expected_version: int,
        target: JobState,
        now: datetime,
        result_code: str | None = None,
    ) -> JobRecord:
        self._validate_time(now)
        self._validate_identity(worker_id, "worker_id")
        if not isinstance(target, JobState):
            raise ValueError("target must be a JobState")
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise JobLifecycleError("job not found")
            self._check_lease(current, worker_id, lease_token, expected_version, now)
            if target not in _ALLOWED_TRANSITIONS[current.state]:
                raise JobLifecycleError(
                    f"transition {current.state.value} -> {target.value} is not allowed"
                )
            lease = None if target in TERMINAL_STATES else current.lease
            updated = replace(
                current,
                state=target,
                lease=lease,
                updated_at=now,
                version=current.version + 1,
                result_code=result_code,
            )
            self._jobs[job_id] = updated
            return updated

    def request_cancel(self, job_id: str, *, owner_id: str, now: datetime) -> JobRecord:
        self._validate_time(now)
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None or not secrets.compare_digest(current.owner_id, owner_id):
                raise JobLifecycleError("job not found")
            if current.state is JobState.QUEUED:
                updated = replace(
                    current,
                    state=JobState.CANCELLED,
                    updated_at=now,
                    version=current.version + 1,
                )
            elif current.state in {JobState.STARTING, JobState.RUNNING}:
                updated = replace(
                    current,
                    state=JobState.CANCEL_REQUESTED,
                    updated_at=now,
                    version=current.version + 1,
                )
            else:
                raise JobLifecycleError("job cannot be cancelled in its current state")
            self._jobs[job_id] = updated
            return updated

    def expire_leases(self, *, now: datetime) -> tuple[str, ...]:
        """Mark lease-expired active jobs UNKNOWN; never automatically re-run them."""
        self._validate_time(now)
        expired: list[str] = []
        with self._lock:
            for job_id, current in tuple(self._jobs.items()):
                if (
                    current.state in _ACTIVE_STATES
                    and current.lease is not None
                    and current.lease.expires_at <= now
                ):
                    self._jobs[job_id] = replace(
                        current,
                        state=JobState.UNKNOWN,
                        lease=None,
                        updated_at=now,
                        version=current.version + 1,
                    )
                    expired.append(job_id)
        return tuple(expired)

    @staticmethod
    def _check_lease(
        current: JobRecord,
        worker_id: str,
        lease_token: str,
        expected_version: int,
        now: datetime,
    ) -> None:
        lease = current.lease
        if (
            lease is None
            or lease.worker_id != worker_id
            or not secrets.compare_digest(lease.token, lease_token)
            or type(expected_version) is not int
            or current.version != expected_version
            or lease.expires_at <= now
        ):
            raise JobLifecycleError("worker lease is invalid, expired, or stale")
