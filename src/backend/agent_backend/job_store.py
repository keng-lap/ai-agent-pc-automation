"""Durable local operational job history (P6-602).

This module stores only bounded operational metadata. It never stores prompts,
model output, secrets, executable paths, command lines, or installer output.
The store is not a worker and exposes no process-dispatch capability.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .job_lifecycle import JobLifecycleError, JobState
from .platform_storage import PlatformStorageUnavailable, create_platform_secure_storage

MAX_PROGRESS_LENGTH = 160
MAX_EVENT_LENGTH = 240
MAX_EVENTS_PER_JOB = 20
MAX_JOBS_PER_QUERY = 25
_VALID_LEVELS = frozenset({"INFO", "WARN", "ERROR"})
_TERMINAL_STATES = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.UNKNOWN}
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


class JobStoreUnavailable(RuntimeError):
    """Durable job storage is unavailable or cannot be trusted."""


class JobStoreConflict(RuntimeError):
    """An idempotency key or lifecycle transition conflicts with existing data."""


def _utc_text(value: datetime | None = None) -> str:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return current.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_text(value: str | None, *, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("text field must be a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise ValueError("text field is empty or exceeds its limit")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in normalized):
        raise ValueError("text field contains control characters")
    return normalized


class SQLiteJobStore:
    """SQLite-backed, transactionally updated job history for one local owner.

    Windows use is intentionally blocked until native DACL/owner/reparse-point
    verification is implemented and independently reviewed. POSIX storage
    requires a private state directory and a non-symlink database path.
    """

    def __init__(self, path: Path | str, *, clock=None, secure_storage=None) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_absolute():
            raise JobStoreUnavailable("Job-store path must be absolute.")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._secure_storage = secure_storage or create_platform_secure_storage()
        try:
            self._secure_storage.prepare_database_path(self.path)
        except PlatformStorageUnavailable as exc:
            raise JobStoreUnavailable(str(exc)) from None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS job_records (
                        job_id TEXT PRIMARY KEY,
                        owner_id TEXT NOT NULL,
                        tool_id TEXT NOT NULL,
                        action_digest TEXT NOT NULL CHECK(length(action_digest) = 64),
                        idempotency_key TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN (
                            'QUEUED','STARTING','RUNNING','VERIFYING',
                            'REBOOT_REQUIRED','CANCEL_REQUESTED','SUCCEEDED',
                            'FAILED','CANCELLED','UNKNOWN'
                        )),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        progress_message TEXT,
                        result_code TEXT,
                        reboot_required INTEGER NOT NULL DEFAULT 0
                            CHECK(reboot_required IN (0,1)),
                        version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
                        UNIQUE(owner_id, idempotency_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_jobs_owner_created
                        ON job_records(owner_id, created_at DESC);
                    CREATE TABLE IF NOT EXISTS job_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL REFERENCES job_records(job_id) ON DELETE CASCADE,
                        occurred_at TEXT NOT NULL,
                        state TEXT NOT NULL,
                        level TEXT NOT NULL CHECK(level IN ('INFO','WARN','ERROR')),
                        message TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_job_events_job_sequence
                        ON job_events(job_id, sequence DESC);
                    PRAGMA user_version = 1;
                    """
                )
            self._secure_storage.finalize_database_file(self.path)
        except JobStoreUnavailable:
            raise
        except PlatformStorageUnavailable as exc:
            raise JobStoreUnavailable(str(exc)) from None
        except (OSError, sqlite3.Error):
            raise JobStoreUnavailable("Job-store database could not be initialized.") from None

    def create(
        self,
        *,
        owner_id: str,
        tool_id: str,
        action_digest: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._validate_identity(owner_id, "owner_id")
        self._validate_identity(tool_id, "tool_id")
        self._validate_identity(idempotency_key, "idempotency_key")
        if (
            not isinstance(action_digest, str)
            or len(action_digest) != 64
            or any(char not in "0123456789abcdef" for char in action_digest)
        ):
            raise ValueError("action_digest must be a lowercase SHA-256 digest")
        timestamp = _utc_text(now or self._clock())
        job_id = str(uuid.uuid4())
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM job_records WHERE owner_id=? AND idempotency_key=?",
                    (owner_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["tool_id"] != tool_id
                        or not secrets.compare_digest(existing["action_digest"], action_digest)
                    ):
                        raise JobStoreConflict("idempotency key was reused for another action")
                    connection.commit()
                    return self._summary(connection, existing)
                connection.execute(
                    """
                    INSERT INTO job_records (
                        job_id, owner_id, tool_id, action_digest, idempotency_key,
                        state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'QUEUED', ?, ?)
                    """,
                    (job_id, owner_id, tool_id, action_digest, idempotency_key, timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO job_events(job_id, occurred_at, state, level, message)
                    VALUES (?, ?, 'QUEUED', 'INFO', 'Job accepted into the local queue')
                    """,
                    (job_id, timestamp),
                )
                connection.commit()
                return self.get_for_owner(job_id, owner_id)
        except (sqlite3.Error, OSError):
            raise JobStoreUnavailable("Job could not be persisted.") from None

    def get_for_owner(self, job_id: str, owner_id: str) -> dict[str, Any]:
        self._validate_identity(owner_id, "owner_id")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT * FROM job_records WHERE job_id=? AND owner_id=?",
                    (job_id, owner_id),
                ).fetchone()
                if row is None:
                    raise JobLifecycleError("job not found")
                return self._summary(connection, row)
        except JobLifecycleError:
            raise
        except (sqlite3.Error, OSError):
            raise JobStoreUnavailable("Job history could not be read.") from None

    def list_for_owner(self, owner_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        self._validate_identity(owner_id, "owner_id")
        if type(limit) is not int or not 1 <= limit <= MAX_JOBS_PER_QUERY:
            raise ValueError("limit must be between 1 and 25")
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM job_records
                    WHERE owner_id=?
                    ORDER BY created_at DESC, job_id DESC
                    LIMIT ?
                    """,
                    (owner_id, limit),
                ).fetchall()
                return [self._summary(connection, row) for row in rows]
        except (sqlite3.Error, OSError):
            raise JobStoreUnavailable("Job history could not be read.") from None

    def update_progress(
        self,
        job_id: str,
        *,
        owner_id: str,
        expected_version: int,
        message: str,
        level: str = "INFO",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        safe_message = _safe_text(message, maximum=MAX_PROGRESS_LENGTH)
        if level not in _VALID_LEVELS:
            raise ValueError("invalid event level")
        timestamp = _utc_text(now or self._clock())
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM job_records WHERE job_id=? AND owner_id=?",
                    (job_id, owner_id),
                ).fetchone()
                if row is None:
                    raise JobLifecycleError("job not found")
                if row["version"] != expected_version:
                    raise JobStoreConflict("job version is stale")
                connection.execute(
                    """
                    UPDATE job_records
                    SET progress_message=?, updated_at=?, version=version+1
                    WHERE job_id=? AND owner_id=? AND version=?
                    """,
                    (safe_message, timestamp, job_id, owner_id, expected_version),
                )
                connection.execute(
                    """
                    INSERT INTO job_events(job_id, occurred_at, state, level, message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job_id, timestamp, row["state"], level, safe_message),
                )
                connection.commit()
                return self.get_for_owner(job_id, owner_id)
        except (JobLifecycleError, JobStoreConflict):
            raise
        except (sqlite3.Error, OSError):
            raise JobStoreUnavailable("Job progress could not be persisted.") from None

    def transition(
        self,
        job_id: str,
        *,
        owner_id: str,
        expected_version: int,
        target: JobState,
        message: str,
        level: str = "INFO",
        result_code: str | None = None,
        reboot_required: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        safe_message = _safe_text(message, maximum=MAX_EVENT_LENGTH)
        if not isinstance(target, JobState) or level not in _VALID_LEVELS:
            raise ValueError("invalid job transition")
        if result_code is not None and (
            not isinstance(result_code, str)
            or not 1 <= len(result_code) <= 64
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in result_code)
        ):
            raise ValueError("invalid result code")
        if type(reboot_required) is not bool:
            raise ValueError("reboot_required must be boolean")
        timestamp = _utc_text(now or self._clock())
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM job_records WHERE job_id=? AND owner_id=?",
                    (job_id, owner_id),
                ).fetchone()
                if row is None:
                    raise JobLifecycleError("job not found")
                if row["version"] != expected_version:
                    raise JobStoreConflict("job version is stale")
                current = JobState(row["state"])
                if target not in _ALLOWED_TRANSITIONS[current]:
                    raise JobStoreConflict("job state transition is not allowed")
                started_at = row["started_at"] or (
                    timestamp if target in {JobState.STARTING, JobState.RUNNING} else None
                )
                finished_at = timestamp if target in _TERMINAL_STATES else None
                connection.execute(
                    """
                    UPDATE job_records
                    SET state=?, updated_at=?, started_at=?, finished_at=?,
                        progress_message=?, result_code=?, reboot_required=?,
                        version=version+1
                    WHERE job_id=? AND owner_id=? AND version=?
                    """,
                    (
                        target.value, timestamp, started_at, finished_at, safe_message,
                        result_code, int(reboot_required), job_id, owner_id, expected_version,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO job_events(job_id, occurred_at, state, level, message)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job_id, timestamp, target.value, level, safe_message),
                )
                connection.commit()
                return self.get_for_owner(job_id, owner_id)
        except (JobLifecycleError, JobStoreConflict):
            raise
        except (sqlite3.Error, OSError):
            raise JobStoreUnavailable("Job transition could not be persisted.") from None

    @staticmethod
    def _validate_identity(value: str, field: str) -> None:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 256
            or value.strip() != value
            or any(ord(char) < 0x21 for char in value)
        ):
            raise ValueError(f"invalid {field}")

    @staticmethod
    def _summary(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        events = connection.execute(
            """
            SELECT sequence, occurred_at, state, level, message
            FROM job_events WHERE job_id=?
            ORDER BY sequence DESC LIMIT ?
            """,
            (row["job_id"], MAX_EVENTS_PER_JOB),
        ).fetchall()
        return {
            "job_id": row["job_id"],
            "tool_id": row["tool_id"],
            "state": row["state"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "progress_message": row["progress_message"],
            "result_code": row["result_code"],
            "reboot_required": bool(row["reboot_required"]),
            "recent_events": [
                {
                    "sequence": event["sequence"],
                    "occurred_at": event["occurred_at"],
                    "state": event["state"],
                    "level": event["level"],
                    "message": event["message"],
                }
                for event in events
            ],
        }
