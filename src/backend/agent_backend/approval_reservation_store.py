"""Durable, non-dispatching approval and job-reservation boundary (P6-609-B2).

This store records a one-use authorization and a reservation receipt only. It
has no worker, queue consumer, process launcher, package-manager, or OS action.
"""

from __future__ import annotations

import secrets
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .platform_storage import PlatformStorageUnavailable, create_platform_secure_storage

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

    The platform adapter must protect the database and its parent directory.
    Tests may inject a test adapter; production callers must use the reviewed
    platform adapter. Windows remains fail-closed until its native ACL adapter
    is implemented and reviewed.
    """

    def __init__(self, path: Path | str, *, clock=None, secure_storage=None) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_absolute():
            raise ApprovalReservationUnavailable("Approval-store path must be absolute.")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._secure_storage = secure_storage or create_platform_secure_storage(path=self.path)
        try:
            self._secure_storage.prepare_database_path(self.path)
            self._initialize()
        except PlatformStorageUnavailable as exc:
            raise ApprovalReservationUnavailable(str(exc)) from None

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
            self._secure_storage.finalize_database_file(self.path)
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
            with self._lock, closing(self._connect()) as connection:
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
        timestamp_value = now or self._clock()
        timestamp = _timestamp(timestamp_value)
        expired = False
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
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
        timestamp = _timestamp(now or self._clock())
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
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
            with closing(self._connect()) as connection:
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
