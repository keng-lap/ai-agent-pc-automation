"""Durable, single-use TOTP step-up challenges (P6-609-B1).

This store persists challenge state and replay counters atomically. It stores no
TOTP secret or submitted code. Platform filesystem protection is delegated to
the same fail-closed adapter contract as the operational job store. It is not
wired into authentication services until the Windows storage gate is reviewed.
"""

from __future__ import annotations

import math
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Literal

from .platform_storage import PlatformStorageUnavailable, create_platform_secure_storage
from .totp import matching_step

ChallengeStatus = Literal["active", "consumed", "invalidated", "expired", "locked"]
_MAX_ATTEMPTS = 5
_MAX_TTL_SECONDS = 300


class DurableStepUpUnavailable(RuntimeError):
    """Durable step-up state cannot be safely read or written."""


class DurableStepUpConflict(RuntimeError):
    """A challenge binding or state conflicts with the requested operation."""


class SQLiteStepUpStore:
    """SQLite-backed challenge and TOTP replay store.

    The transaction that consumes a challenge also advances the owner's TOTP
    replay counter. BEGIN IMMEDIATE plus a unique owner row serializes competing
    processes. Callers must not treat this class as enabled on platforms where
    the secure-storage adapter is unavailable.
    """

    def __init__(self, path: Path | str, *, secure_storage=None, clock=None) -> None:
        self.path = Path(path).expanduser()
        if not self.path.is_absolute():
            raise DurableStepUpUnavailable("Step-up database path must be absolute.")
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._secure_storage = secure_storage or create_platform_secure_storage()
        try:
            self._secure_storage.prepare_database_path(self.path)
            with self._lock, closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS step_up_challenges (
                        challenge_id TEXT PRIMARY KEY,
                        owner_sub TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL,
                        action_digest TEXT NOT NULL CHECK(length(action_digest)=64),
                        risk_class TEXT NOT NULL CHECK(risk_class='high'),
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        failed_attempts INTEGER NOT NULL DEFAULT 0
                            CHECK(failed_attempts BETWEEN 0 AND 5),
                        status TEXT NOT NULL CHECK(status IN (
                            'active','consumed','invalidated','expired','locked'
                        ))
                    );
                    CREATE INDEX IF NOT EXISTS idx_step_up_owner_session
                        ON step_up_challenges(owner_sub, session_id, created_at);
                    CREATE TABLE IF NOT EXISTS totp_replay_counters (
                        owner_sub TEXT PRIMARY KEY,
                        last_step INTEGER NOT NULL CHECK(last_step >= 0),
                        updated_at REAL NOT NULL
                    );
                    PRAGMA user_version = 1;
                    """
                )
            self._secure_storage.finalize_database_file(self.path)
        except (PlatformStorageUnavailable, OSError, sqlite3.Error):
            raise DurableStepUpUnavailable(
                "Durable step-up storage is unavailable or cannot be trusted."
            ) from None

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=5.0, isolation_level=None, check_same_thread=False
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def create(
        self,
        *,
        owner_sub: str,
        session_id: str,
        plan_id: str,
        action_digest: str,
        risk_class: str,
        ttl_seconds: int = 120,
    ) -> dict[str, object]:
        self._validate_identity(owner_sub, "owner")
        self._validate_identity(session_id, "session")
        if not isinstance(plan_id, str) or len(plan_id) != 32 or any(
            char not in "0123456789abcdef" for char in plan_id
        ):
            raise ValueError("invalid plan identifier")
        if not isinstance(action_digest, str) or len(action_digest) != 64 or any(
            char not in "0123456789abcdef" for char in action_digest
        ):
            raise ValueError("invalid action digest")
        if risk_class != "high":
            raise ValueError("step-up challenge is required only for high-risk actions")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("challenge TTL must be between 1 and 300 seconds")
        now = self._now()
        challenge_id = secrets.token_hex(16)
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """INSERT INTO step_up_challenges
                    (challenge_id, owner_sub, session_id, plan_id, action_digest,
                     risk_class, created_at, expires_at, status)
                    VALUES (?, ?, ?, ?, ?, 'high', ?, ?, 'active')""",
                    (challenge_id, owner_sub, session_id, plan_id, action_digest,
                     now, now + ttl_seconds),
                )
                connection.commit()
        except (sqlite3.Error, OSError):
            raise DurableStepUpUnavailable("Step-up challenge could not be persisted.") from None
        return {
            "challenge_id": challenge_id,
            "expires_at": now + ttl_seconds,
            "plan_id": plan_id,
            "action_digest": action_digest,
        }

    def verify_and_consume(
        self,
        *,
        challenge_id: str,
        owner_sub: str,
        session_id: str,
        plan_id: str,
        action_digest: str,
        risk_class: str,
        code: str,
        secret_loader: Callable[[], str | None],
    ) -> bool:
        """Verify a code and atomically consume challenge plus replay step."""
        if not self._valid_identity(owner_sub, session_id) or not callable(secret_loader):
            return False
        now = self._now()
        try:
            with self._lock, closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                challenge = connection.execute(
                    "SELECT * FROM step_up_challenges WHERE challenge_id=?",
                    (challenge_id,),
                ).fetchone()
                if challenge is None or challenge["status"] != "active":
                    connection.rollback()
                    return False
                if challenge["expires_at"] <= now:
                    connection.execute(
                        "UPDATE step_up_challenges SET status='expired' WHERE challenge_id=? AND status='active'",
                        (challenge_id,),
                    )
                    connection.commit()
                    return False
                if (
                    challenge["owner_sub"] != owner_sub
                    or challenge["session_id"] != session_id
                ):
                    connection.rollback()
                    return False
                if (
                    challenge["plan_id"] != plan_id
                    or challenge["action_digest"] != action_digest
                    or challenge["risk_class"] != risk_class
                ):
                    connection.execute(
                        "UPDATE step_up_challenges SET status='invalidated' WHERE challenge_id=? AND status='active'",
                        (challenge_id,),
                    )
                    connection.commit()
                    return False

                secret = secret_loader()
                step = matching_step(secret, code, timestamp=now) if isinstance(secret, str) else None
                if step is None:
                    attempts = challenge["failed_attempts"] + 1
                    status = "locked" if attempts >= _MAX_ATTEMPTS else "active"
                    connection.execute(
                        "UPDATE step_up_challenges SET failed_attempts=?, status=? WHERE challenge_id=? AND status='active'",
                        (attempts, status, challenge_id),
                    )
                    connection.commit()
                    return False

                previous = connection.execute(
                    "SELECT last_step FROM totp_replay_counters WHERE owner_sub=?",
                    (owner_sub,),
                ).fetchone()
                if previous is not None and step <= previous["last_step"]:
                    connection.rollback()
                    return False
                connection.execute(
                    """INSERT INTO totp_replay_counters(owner_sub,last_step,updated_at)
                    VALUES(?,?,?) ON CONFLICT(owner_sub) DO UPDATE SET
                    last_step=excluded.last_step, updated_at=excluded.updated_at""",
                    (owner_sub, step, now),
                )
                changed = connection.execute(
                    "UPDATE step_up_challenges SET status='consumed' WHERE challenge_id=? AND status='active'",
                    (challenge_id,),
                ).rowcount
                if changed != 1:
                    connection.rollback()
                    return False
                connection.commit()
                return True
        except (sqlite3.Error, OSError):
            raise DurableStepUpUnavailable("Step-up verification could not be persisted.") from None

    def get_status(self, challenge_id: str) -> str | None:
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT status FROM step_up_challenges WHERE challenge_id=?",
                    (challenge_id,),
                ).fetchone()
                return row["status"] if row else None
        except (sqlite3.Error, OSError):
            raise DurableStepUpUnavailable("Step-up challenge state could not be read.") from None

    def _now(self) -> float:
        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            raise DurableStepUpUnavailable("System clock is invalid.")
        return float(now)

    @staticmethod
    def _validate_identity(value: str, field: str) -> None:
        if (\n            not isinstance(value, str)\n            or not value\n            or len(value) > (256 if field == "owner" else 128)\n            or value.strip() != value\n            or any(ord(char) < 0x21 for char in value)\n        ):
            raise ValueError(f"invalid {field}")

    @staticmethod
    def _valid_identity(owner_sub: str, session_id: str) -> bool:
        return (
            isinstance(owner_sub, str) and 1 <= len(owner_sub) <= 256
            and owner_sub.strip() == owner_sub and not any(ord(c) < 0x21 for c in owner_sub)
            and isinstance(session_id, str) and 1 <= len(session_id) <= 128
            and session_id.strip() == session_id and not any(ord(c) < 0x21 for c in session_id)
        )
