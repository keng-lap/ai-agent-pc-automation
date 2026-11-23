"""Durable approval, reservation, and one-shot install queue (P6-609-C).

The store persists exact approved payloads and worker leases. It does not itself
launch processes or invoke a package manager; those actions belong to the
separately contained Windows worker.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .platform_storage import PlatformStorageUnavailable, create_platform_secure_storage
from .software_approval import InstallApprovalBinding

_DIGEST_LENGTH = 64
_PLAN_ID_LENGTH = 32


class ApprovalReservationError(RuntimeError):
    """Base class for rejected durable approval/reservation operations."""


class ApprovalReservationConflict(ApprovalReservationError):
    """The approval, idempotency binding, or lifecycle state conflicts."""


class ApprovalReservationExpired(ApprovalReservationError):
    """The approval expired before a reservation could be created."""


class ApprovalReservationNotFound(ApprovalReservationError):
    """The requested approval or owner-scoped reservation does not exist."""


class ApprovalReservationUnavailable(ApprovalReservationError):
    """The durable store is unavailable or cannot be trusted."""


@dataclass(frozen=True, slots=True)
class ReservationReceipt:
    """Stable metadata receipt; deliberately contains no dispatch capability."""

    reservation_id: str
    approval_id: str
    plan_id: str
    action_digest: str
    state: str
    created_at: str

@dataclass(frozen=True, slots=True)
class InstallExecutionJob:
    """Durable one-shot worker claim and exact approval payload."""

    reservation_id: str
    owner_id: str
    action_digest: str
    binding_json: str
    state: str
    worker_id: str | None
    lease_token: str | None
    lease_expires_at: str | None
    attempts: int
    version: int
    result_code: str | None


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identity(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or value.strip() != value
        or any(ord(char) < 0x21 for char in value)
    ):
        raise ValueError(f"invalid {field}")


def _hex(value: str, length: int, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{field} must be lowercase hexadecimal")


class SQLiteApprovalReservationStore:
    """SQLite store for exact-action approval consumption and inert reservations.

    Every SQLite connection is enclosed by the platform adapter's protection
    lease. Tests may inject a test adapter; production callers must use the
    platform-selected adapter.
    """

    def __init__(self, path: Path | str, *, clock=None, secure_storage=None) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_absolute():
            raise ApprovalReservationUnavailable("Approval-store path must be absolute.")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._secure_storage = secure_storage or create_platform_secure_storage()
        try:
            self._initialize()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Release platform storage handles after all database operations stop."""
        close = getattr(self._secure_storage, "close", None)
        if close is not None:
            close()

    @contextmanager
    def _connection(self, *, require_wal: bool = True) -> Iterator[sqlite3.Connection]:
        """Keep the platform protection lease alive for the SQLite connection."""
        try:
            with self._secure_storage.protect_database(self.path) as lease:
                connection = sqlite3.connect(
                    self.path,
                    timeout=5.0,
                    isolation_level=None,
                    check_same_thread=False,
                )
                try:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA foreign_keys = ON")
                    connection.execute("PRAGMA busy_timeout = 5000")
                    connection.execute("PRAGMA synchronous = FULL")
                    if require_wal:
                        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
                        if not journal_mode or str(journal_mode[0]).lower() != "wal":
                            raise ApprovalReservationUnavailable(
                                "Approval database is not in the required WAL mode."
                            )
                    lease.verify()
                    yield connection
                    lease.verify()
                finally:
                    connection.close()
        except PlatformStorageUnavailable as exc:
            raise ApprovalReservationUnavailable(str(exc)) from None

    def _initialize(self) -> None:
        try:
            with self._lock, self._connection(require_wal=False) as connection:
                journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
                if not journal_mode or str(journal_mode[0]).lower() != "wal":
                    raise ApprovalReservationUnavailable(
                        "Approval database could not enter required WAL mode."
                    )
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS approval_records (
                        approval_id TEXT PRIMARY KEY,
                        owner_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL CHECK(length(plan_id) = 32),
                        plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
                        action_digest TEXT NOT NULL CHECK(length(action_digest) = 64),
                        evidence_expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN (
                            'ACTIVE', 'RESERVED', 'EXPIRED', 'REVOKED'
                        )),
                        version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0)
                    );
                    CREATE INDEX IF NOT EXISTS idx_approval_owner_created
                        ON approval_records(owner_id, created_at DESC);
                    CREATE TABLE IF NOT EXISTS job_reservations (
                        reservation_id TEXT PRIMARY KEY,
                        approval_id TEXT NOT NULL UNIQUE
                            REFERENCES approval_records(approval_id),
                        owner_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL CHECK(length(plan_id) = 32),
                        plan_digest TEXT NOT NULL CHECK(length(plan_digest) = 64),
                        action_digest TEXT NOT NULL CHECK(length(action_digest) = 64),
                        idempotency_key TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state = 'RESERVED'),
                        created_at TEXT NOT NULL,
                        UNIQUE(owner_id, idempotency_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_reservation_owner_created
                        ON job_reservations(owner_id, created_at DESC);
                    CREATE TABLE IF NOT EXISTS install_execution_jobs (
                        reservation_id TEXT PRIMARY KEY
                            REFERENCES job_reservations(reservation_id),
                        owner_id TEXT NOT NULL,
                        action_digest TEXT NOT NULL CHECK(length(action_digest) = 64),
                        binding_json TEXT NOT NULL CHECK(length(binding_json) BETWEEN 2 AND 65536),
                        state TEXT NOT NULL CHECK(state IN (
                            'QUEUED', 'CLAIMED', 'RUNNING', 'VERIFYING',
                            'SUCCEEDED', 'FAILED', 'REBOOT_REQUIRED', 'UNKNOWN'
                        )),
                        worker_id TEXT,
                        lease_token TEXT,
                        lease_expires_at TEXT,
                        attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 1),
                        version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
                        result_code TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_install_jobs_queue
                        ON install_execution_jobs(state, created_at);
                    CREATE TABLE IF NOT EXISTS real_install_release_consumptions (
                        nonce TEXT PRIMARY KEY CHECK(length(nonce) = 64),
                        task_id TEXT NOT NULL,
                        package_id TEXT NOT NULL,
                        package_version TEXT NOT NULL,
                        action_digest TEXT NOT NULL CHECK(length(action_digest) = 64),
                        expires_at TEXT NOT NULL,
                        consumed_at TEXT NOT NULL
                    );
                    CREATE TRIGGER IF NOT EXISTS real_install_release_no_update
                    BEFORE UPDATE ON real_install_release_consumptions
                    BEGIN
                        SELECT RAISE(ABORT, 'release authorizations are append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS real_install_release_no_delete
                    BEFORE DELETE ON real_install_release_consumptions
                    BEGIN
                        SELECT RAISE(ABORT, 'release authorizations are append-only');
                    END;
                    CREATE TABLE IF NOT EXISTS install_execution_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        reservation_id TEXT NOT NULL
                            REFERENCES install_execution_jobs(reservation_id),
                        state TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        outcome TEXT NOT NULL CHECK(outcome IN ('success', 'denied')),
                        result_code TEXT
                    );
                    CREATE TRIGGER IF NOT EXISTS install_execution_payload_immutable
                    BEFORE UPDATE OF reservation_id, owner_id, action_digest,
                        binding_json, created_at
                    ON install_execution_jobs
                    BEGIN
                        SELECT RAISE(ABORT, 'install execution payload is immutable');
                    END;
                    CREATE TRIGGER IF NOT EXISTS install_execution_events_no_update
                    BEFORE UPDATE ON install_execution_events
                    BEGIN
                        SELECT RAISE(ABORT, 'install execution events are append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS install_execution_events_no_delete
                    BEFORE DELETE ON install_execution_events
                    BEGIN
                        SELECT RAISE(ABORT, 'install execution events are append-only');
                    END;
                    CREATE TABLE IF NOT EXISTS approval_audit_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        approval_id TEXT NOT NULL
                            REFERENCES approval_records(approval_id),
                        event_type TEXT NOT NULL CHECK(event_type IN (
                            'approval.created', 'approval.reserved',
                            'approval.expired', 'approval.revoked'
                        )),
                        outcome TEXT NOT NULL CHECK(outcome IN ('success', 'denied')),
                        occurred_at TEXT NOT NULL,
                        reason TEXT CHECK(reason IS NULL OR reason IN (
                            'evidence_expired', 'owner_revoked'
                        ))
                    );
                    CREATE INDEX IF NOT EXISTS idx_approval_audit_approval
                        ON approval_audit_events(approval_id, sequence);

                    -- Approval identity and evidence bindings never change after
                    -- creation. Only the lifecycle state/version may advance.
                    CREATE TRIGGER IF NOT EXISTS approval_bindings_immutable
                    BEFORE UPDATE OF approval_id, owner_id, session_id, plan_id,
                        plan_digest, action_digest, evidence_expires_at, created_at
                    ON approval_records
                    BEGIN
                        SELECT RAISE(ABORT, 'approval bindings are immutable');
                    END;
                    CREATE TRIGGER IF NOT EXISTS approval_records_no_delete
                    BEFORE DELETE ON approval_records
                    BEGIN
                        SELECT RAISE(ABORT, 'approval records cannot be deleted');
                    END;
                    CREATE TRIGGER IF NOT EXISTS approval_audit_no_update
                    BEFORE UPDATE ON approval_audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'approval audit is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS approval_audit_no_delete
                    BEFORE DELETE ON approval_audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'approval audit is append-only');
                    END;
                    CREATE TRIGGER IF NOT EXISTS reservations_no_update
                    BEFORE UPDATE ON job_reservations
                    BEGIN
                        SELECT RAISE(ABORT, 'reservation receipts are immutable');
                    END;
                    CREATE TRIGGER IF NOT EXISTS reservations_no_delete
                    BEFORE DELETE ON job_reservations
                    BEGIN
                        SELECT RAISE(ABORT, 'reservation receipts cannot be deleted');
                    END;
                    PRAGMA user_version = 1;
                    """
                )
        except (sqlite3.Error, OSError, PlatformStorageUnavailable):
            raise ApprovalReservationUnavailable(
                "Approval reservation database could not be initialized securely."
            ) from None

    def create_approval(
        self,
        *,
        approval_id: str,
        owner_id: str,
        session_id: str,
        plan_id: str,
        plan_digest: str,
        action_digest: str,
        evidence_expires_at: datetime,
        now: datetime | None = None,
    ) -> None:
        """Persist a fresh exact-action approval before it can be consumed."""
        _identity(approval_id, "approval_id")
        _identity(owner_id, "owner_id")
        _identity(session_id, "session_id")
        _hex(plan_id, _PLAN_ID_LENGTH, "plan_id")
        _hex(plan_digest, _DIGEST_LENGTH, "plan_digest")
        _hex(action_digest, _DIGEST_LENGTH, "action_digest")
        created = _timestamp(now or self._clock())
        expires = _timestamp(evidence_expires_at)
        if expires <= created:
            raise ApprovalReservationExpired("approval evidence is already expired")
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO approval_records (
                        approval_id, owner_id, session_id, plan_id, plan_digest,
                        action_digest, evidence_expires_at, created_at, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                    """,
                    (
                        approval_id, owner_id, session_id, plan_id, plan_digest,
                        action_digest, expires, created,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO approval_audit_events (
                        approval_id, event_type, outcome, occurred_at
                    ) VALUES (?, 'approval.created', 'success', ?)
                    """,
                    (approval_id, created),
                )
                connection.commit()
        except sqlite3.IntegrityError:
            raise ApprovalReservationConflict("approval identifier already exists") from None
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Approval could not be persisted.") from None

    def reserve(
        self,
        *,
        approval_id: str,
        owner_id: str,
        session_id: str,
        plan_id: str,
        plan_digest: str,
        action_digest: str,
        idempotency_key: str,
        binding_json: str | None = None,
        now: datetime | None = None,
    ) -> ReservationReceipt:
        """Consume an active approval and persist one inert reservation atomically."""
        _identity(approval_id, "approval_id")
        _identity(owner_id, "owner_id")
        _identity(session_id, "session_id")
        _identity(idempotency_key, "idempotency_key")
        _hex(plan_id, _PLAN_ID_LENGTH, "plan_id")
        _hex(plan_digest, _DIGEST_LENGTH, "plan_digest")
        _hex(action_digest, _DIGEST_LENGTH, "action_digest")
        if binding_json is not None:
            if not isinstance(binding_json, str) or len(binding_json) > 65536:
                raise ValueError("binding_json is invalid or too large")
            try:
                binding = InstallApprovalBinding.model_validate_json(binding_json)
            except ValueError:
                raise ValueError("binding_json is not a valid install approval") from None
            if binding.approval_digest != action_digest or binding.plan_digest != plan_digest:
                raise ApprovalReservationConflict("serialized install binding does not match reservation")
        expired = False
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = _timestamp(now if now is not None else self._clock())
                prior = connection.execute(
                    """
                    SELECT * FROM job_reservations
                    WHERE owner_id=? AND idempotency_key=?
                    """,
                    (owner_id, idempotency_key),
                ).fetchone()
                if prior is not None:
                    if (
                        prior["approval_id"] != approval_id
                        or prior["session_id"] != session_id
                        or prior["plan_id"] != plan_id
                        or prior["plan_digest"] != plan_digest
                        or prior["action_digest"] != action_digest
                    ):
                        raise ApprovalReservationConflict(
                            "idempotency key is bound to a different reservation"
                        )
                    connection.commit()
                    return self._receipt(prior)

                approval = connection.execute(
                    "SELECT * FROM approval_records WHERE approval_id=?",
                    (approval_id,),
                ).fetchone()
                if approval is None:
                    raise ApprovalReservationNotFound("approval not found")
                expected = (
                    approval["owner_id"] == owner_id
                    and approval["session_id"] == session_id
                    and approval["plan_id"] == plan_id
                    and secrets.compare_digest(approval["plan_digest"], plan_digest)
                    and secrets.compare_digest(approval["action_digest"], action_digest)
                )
                if not expected:
                    raise ApprovalReservationConflict("approval binding does not match request")
                if approval["state"] == "REVOKED":
                    raise ApprovalReservationConflict("approval has been revoked")
                if approval["state"] == "EXPIRED":
                    raise ApprovalReservationExpired("approval has expired")
                if approval["state"] == "RESERVED":
                    raise ApprovalReservationConflict("approval was consumed by another request")
                if timestamp >= approval["evidence_expires_at"]:
                    connection.execute(
                        """
                        UPDATE approval_records
                        SET state='EXPIRED', version=version+1
                        WHERE approval_id=? AND state='ACTIVE'
                        """,
                        (approval_id,),
                    )
                    connection.execute(
                        """
                        INSERT INTO approval_audit_events (
                            approval_id, event_type, outcome, occurred_at, reason
                        ) VALUES (?, 'approval.expired', 'denied', ?, 'evidence_expired')
                        """,
                        (approval_id, timestamp),
                    )
                    connection.commit()
                    expired = True
                else:
                    reservation_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO job_reservations (
                            reservation_id, approval_id, owner_id, session_id,
                            plan_id, plan_digest, action_digest, idempotency_key,
                            state, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RESERVED', ?)
                        """,
                        (
                            reservation_id, approval_id, owner_id, session_id,
                            plan_id, plan_digest, action_digest, idempotency_key,
                            timestamp,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE approval_records
                        SET state='RESERVED', version=version+1
                        WHERE approval_id=? AND state='ACTIVE'
                        """,
                        (approval_id,),
                    )
                    if binding_json is not None:
                        connection.execute(
                            """
                            INSERT INTO install_execution_jobs (
                                reservation_id, owner_id, action_digest, binding_json,
                                state, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?)
                            """,
                            (reservation_id, owner_id, action_digest, binding_json, timestamp, timestamp),
                        )
                        connection.execute(
                            """
                            INSERT INTO install_execution_events (
                                reservation_id, state, occurred_at, outcome
                            ) VALUES (?, 'QUEUED', ?, 'success')
                            """,
                            (reservation_id, timestamp),
                        )
                    connection.execute(
                        """
                        INSERT INTO approval_audit_events (
                            approval_id, event_type, outcome, occurred_at
                        ) VALUES (?, 'approval.reserved', 'success', ?)
                        """,
                        (approval_id, timestamp),
                    )
                    row = connection.execute(
                        "SELECT * FROM job_reservations WHERE reservation_id=?",
                        (reservation_id,),
                    ).fetchone()
                    connection.commit()
                    return self._receipt(row)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Reservation could not be persisted.") from None
        if expired:
            raise ApprovalReservationExpired("approval evidence expired before reservation")
        raise ApprovalReservationUnavailable("Reservation did not reach a stable state.")

    def revoke(self, *, approval_id: str, owner_id: str, now: datetime | None = None) -> None:
        """Revoke an unused approval; reservation and revocation serialize in SQLite."""
        _identity(approval_id, "approval_id")
        _identity(owner_id, "owner_id")
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = _timestamp(now if now is not None else self._clock())
                row = connection.execute(
                    "SELECT state FROM approval_records WHERE approval_id=? AND owner_id=?",
                    (approval_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("approval not found")
                if row["state"] != "ACTIVE":
                    raise ApprovalReservationConflict("approval is no longer revocable")
                connection.execute(
                    """
                    UPDATE approval_records SET state='REVOKED', version=version+1
                    WHERE approval_id=? AND owner_id=? AND state='ACTIVE'
                    """,
                    (approval_id, owner_id),
                )
                connection.execute(
                    """
                    INSERT INTO approval_audit_events (
                        approval_id, event_type, outcome, occurred_at, reason
                    ) VALUES (?, 'approval.revoked', 'success', ?, 'owner_revoked')
                    """,
                    (approval_id, timestamp),
                )
                connection.commit()
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable(
                "Approval revocation could not be persisted."
            ) from None

    def get_reservation(
        self, *, reservation_id: str, owner_id: str
    ) -> ReservationReceipt:
        _identity(owner_id, "owner_id")
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM job_reservations
                    WHERE reservation_id=? AND owner_id=?
                    """,
                    (reservation_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("reservation not found")
                return self._receipt(row)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Reservation could not be read.") from None


    def claim_next_install(
        self, *, worker_id: str, now: datetime | None = None, lease_seconds: int = 60
    ) -> InstallExecutionJob | None:
        """Atomically claim one queued install. A lost lease becomes UNKNOWN, never retried."""
        _identity(worker_id, "worker_id")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = now if now is not None else self._clock()
                timestamp = _timestamp(current)
                expires = _timestamp(current + timedelta(seconds=lease_seconds))
                expired = connection.execute(
                    """
                    SELECT reservation_id FROM install_execution_jobs
                    WHERE state IN ('CLAIMED','RUNNING','VERIFYING','REBOOT_REQUIRED')
                      AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
                    """,
                    (timestamp,),
                ).fetchall()
                for row in expired:
                    connection.execute(
                        """
                        UPDATE install_execution_jobs
                        SET state='UNKNOWN', worker_id=NULL, lease_token=NULL,
                            lease_expires_at=NULL, version=version+1,
                            result_code='WORKER_LEASE_EXPIRED', updated_at=?
                        WHERE reservation_id=?
                        """,
                        (timestamp, row["reservation_id"]),
                    )
                    connection.execute(
                        """
                        INSERT INTO install_execution_events
                            (reservation_id, state, occurred_at, outcome, result_code)
                        VALUES (?, 'UNKNOWN', ?, 'denied', 'WORKER_LEASE_EXPIRED')
                        """,
                        (row["reservation_id"], timestamp),
                    )
                row = connection.execute(
                    """
                    SELECT * FROM install_execution_jobs
                    WHERE state='QUEUED' AND attempts=0
                    ORDER BY created_at, reservation_id LIMIT 1
                    """
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                token = secrets.token_urlsafe(32)
                connection.execute(
                    """
                    UPDATE install_execution_jobs
                    SET state='CLAIMED', worker_id=?, lease_token=?,
                        lease_expires_at=?, attempts=1, version=version+1, updated_at=?
                    WHERE reservation_id=? AND state='QUEUED' AND attempts=0
                    """,
                    (worker_id, token, expires, timestamp, row["reservation_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO install_execution_events
                        (reservation_id, state, occurred_at, outcome)
                    VALUES (?, 'CLAIMED', ?, 'success')
                    """,
                    (row["reservation_id"], timestamp),
                )
                claimed = connection.execute(
                    "SELECT * FROM install_execution_jobs WHERE reservation_id=?",
                    (row["reservation_id"],),
                ).fetchone()
                connection.commit()
                return self._execution_job(claimed)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Install job could not be claimed.") from None

    def renew_install_lease(
        self, reservation_id: str, *, worker_id: str, lease_token: str,
        expected_version: int, lease_seconds: int = 60, now: datetime | None = None,
    ) -> InstallExecutionJob:
        """Renew a live worker lease without changing the one-shot attempt count."""
        _identity(worker_id, "worker_id")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 300:
            raise ValueError("lease_seconds must be between 1 and 300")
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = now if now is not None else self._clock()
                timestamp = _timestamp(current)
                expires = _timestamp(current + timedelta(seconds=lease_seconds))
                row = connection.execute(
                    "SELECT * FROM install_execution_jobs WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("install job not found")
                if (
                    row["worker_id"] != worker_id
                    or not secrets.compare_digest(row["lease_token"] or "", lease_token)
                    or row["version"] != expected_version
                    or row["lease_expires_at"] is None
                    or row["lease_expires_at"] <= timestamp
                    or row["state"] not in {"CLAIMED", "RUNNING", "VERIFYING", "REBOOT_REQUIRED"}
                ):
                    raise ApprovalReservationConflict("install worker lease is stale or expired")
                connection.execute(
                    """
                    UPDATE install_execution_jobs
                    SET lease_expires_at=?, version=version+1, updated_at=?
                    WHERE reservation_id=? AND version=?
                    """,
                    (expires, timestamp, reservation_id, expected_version),
                )
                connection.execute(
                    """
                    INSERT INTO install_execution_events
                        (reservation_id, state, occurred_at, outcome)
                    VALUES (?, ?, ?, 'success')
                    """,
                    (reservation_id, row["state"], timestamp),
                )
                updated = connection.execute(
                    "SELECT * FROM install_execution_jobs WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                connection.commit()
                return self._execution_job(updated)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Install worker lease could not be renewed.") from None

    def transition_install(
        self, reservation_id: str, *, worker_id: str, lease_token: str,
        expected_version: int, target: str, result_code: str | None = None,
        now: datetime | None = None,
    ) -> InstallExecutionJob:
        allowed = {
            "CLAIMED": {"RUNNING", "FAILED", "UNKNOWN"},
            "RUNNING": {"VERIFYING", "FAILED", "REBOOT_REQUIRED", "UNKNOWN"},
            "VERIFYING": {"SUCCEEDED", "FAILED", "REBOOT_REQUIRED", "UNKNOWN"},
            "REBOOT_REQUIRED": {"VERIFYING", "UNKNOWN"},
        }
        if target not in {"RUNNING", "VERIFYING", "SUCCEEDED", "FAILED", "REBOOT_REQUIRED", "UNKNOWN"}:
            raise ValueError("invalid install job state")
        if result_code is not None and (
            not isinstance(result_code, str) or not 1 <= len(result_code) <= 64
            or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in result_code)
        ):
            raise ValueError("invalid result code")
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = _timestamp(now if now is not None else self._clock())
                row = connection.execute(
                    "SELECT * FROM install_execution_jobs WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("install job not found")
                if (
                    row["worker_id"] != worker_id
                    or not secrets.compare_digest(row["lease_token"] or "", lease_token)
                    or row["version"] != expected_version
                    or row["lease_expires_at"] is None
                    or row["lease_expires_at"] <= timestamp
                ):
                    raise ApprovalReservationConflict("install worker lease is stale or expired")
                if target not in allowed.get(row["state"], set()):
                    raise ApprovalReservationConflict("install job transition is not allowed")
                terminal = target in {"SUCCEEDED", "FAILED", "UNKNOWN"}
                connection.execute(
                    """
                    UPDATE install_execution_jobs
                    SET state=?, result_code=?, worker_id=?, lease_token=?,
                        lease_expires_at=?, version=version+1, updated_at=?
                    WHERE reservation_id=? AND version=?
                    """,
                    (
                        target, result_code, None if terminal else worker_id,
                        None if terminal else lease_token,
                        None if terminal else row["lease_expires_at"],
                        timestamp, reservation_id, expected_version,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO install_execution_events
                        (reservation_id, state, occurred_at, outcome, result_code)
                    VALUES (?, ?, ?, 'success', ?)
                    """,
                    (reservation_id, target, timestamp, result_code),
                )
                updated = connection.execute(
                    "SELECT * FROM install_execution_jobs WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                connection.commit()
                return self._execution_job(updated)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Install job transition could not be persisted.") from None

    def consume_real_install_release_authorization(
        self, *, task_id: str, package_id: str, version: str,
        action_digest: str, nonce: str, expires_at: datetime, now: datetime | None = None,
    ) -> None:
        """Atomically consume a one-use release nonce for one exact approved install binding."""
        if task_id != "P6-609-C":
            raise ApprovalReservationConflict("release authorization task does not match")
        _identity(package_id, "package_id")
        _identity(version, "version")
        _hex(action_digest, _DIGEST_LENGTH, "action_digest")
        _hex(nonce, 64, "release_nonce")
        expiry = _timestamp(expires_at)
        try:
            with self._lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                current = now if now is not None else self._clock()
                timestamp = _timestamp(current)
                if expiry <= timestamp:
                    raise ApprovalReservationExpired("release authorization has expired")
                connection.execute(
                    """
                    INSERT INTO real_install_release_consumptions (
                        nonce, task_id, package_id, package_version,
                        action_digest, expires_at, consumed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (nonce, task_id, package_id, version, action_digest, expiry, timestamp),
                )
                connection.commit()
        except sqlite3.IntegrityError:
            raise ApprovalReservationConflict("release authorization nonce was already consumed") from None
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Real-install release authorization could not be consumed.") from None
    def get_install_job_for_plan(self, *, plan_id: str, owner_id: str) -> InstallExecutionJob:
        """Recover the existing install job for an owner-scoped plan without dispatching it."""
        _identity(owner_id, "owner_id")
        _hex(plan_id, _PLAN_ID_LENGTH, "plan_id")
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT jobs.* FROM install_execution_jobs AS jobs
                    INNER JOIN job_reservations AS reservations
                        ON reservations.reservation_id = jobs.reservation_id
                    WHERE reservations.owner_id=? AND reservations.plan_id=?
                    ORDER BY reservations.created_at DESC LIMIT 1
                    """,
                    (owner_id, plan_id),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("install job not found")
                return self._execution_job(row)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Install job could not be recovered.") from None

    def get_install_job(self, *, reservation_id: str, owner_id: str) -> InstallExecutionJob:
        _identity(owner_id, "owner_id")
        try:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM install_execution_jobs
                    WHERE reservation_id=? AND owner_id=?
                    """,
                    (reservation_id, owner_id),
                ).fetchone()
                if row is None:
                    raise ApprovalReservationNotFound("install job not found")
                return self._execution_job(row)
        except ApprovalReservationError:
            raise
        except sqlite3.Error:
            raise ApprovalReservationUnavailable("Install job could not be read.") from None

    @staticmethod
    def _execution_job(row: sqlite3.Row) -> InstallExecutionJob:
        return InstallExecutionJob(
            reservation_id=row["reservation_id"], owner_id=row["owner_id"],
            action_digest=row["action_digest"], binding_json=row["binding_json"],
            state=row["state"], worker_id=row["worker_id"],
            lease_token=row["lease_token"], lease_expires_at=row["lease_expires_at"],
            attempts=row["attempts"], version=row["version"], result_code=row["result_code"],
        )

    @staticmethod
    def _receipt(row: sqlite3.Row) -> ReservationReceipt:
        return ReservationReceipt(
            reservation_id=row["reservation_id"],
            approval_id=row["approval_id"],
            plan_id=row["plan_id"],
            action_digest=row["action_digest"],
            state=row["state"],
            created_at=row["created_at"],
        )
