"""Exact-action-bound TOTP challenges (W4, provider independent).

This bounded in-memory implementation is a contract/core for the later auth
integration. It is not wired to the existing P1 dry-run route. A production
multi-worker deployment requires shared atomic challenge and replay storage.
"""

from __future__ import annotations

import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal

from .totp import TotpReplayGuard

ChallengeStatus = Literal["active", "consumed", "invalidated", "expired", "locked"]
PLAN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ACTION_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

CHALLENGE_TTL_SECONDS = 120
MAX_CHALLENGES = 128
MAX_FAILED_ATTEMPTS = 5


@dataclass(frozen=True, slots=True)
class StepUpChallenge:
    """Immutable binding for one high-risk action confirmation."""

    challenge_id: str
    owner_sub: str
    session_id: str
    plan_id: str
    action_digest: str
    risk_class: str
    created_at: float
    expires_at: float
    failed_attempts: int = 0
    status: ChallengeStatus = "active"


@dataclass(frozen=True, slots=True)
class StepUpChallengeReceipt:
    """Safe client-facing challenge metadata; contains no authenticator secret."""

    challenge_id: str
    expires_at: float
    plan_id: str
    action_digest: str


class StepUpChallengeStore:
    """Thread-safe, bounded, process-local exact-action challenge store."""

    def __init__(
        self,
        *,
        replay_guard: TotpReplayGuard | None = None,
        clock=None,
        ttl_seconds: int = CHALLENGE_TTL_SECONDS,
        capacity: int = MAX_CHALLENGES,
    ) -> None:
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 300:
            raise ValueError("challenge TTL must be between 1 and 300 seconds")
        if type(capacity) is not int or not 1 <= capacity <= MAX_CHALLENGES:
            raise ValueError("challenge capacity must be between 1 and 128")
        self._replay_guard = replay_guard or TotpReplayGuard()
        self._clock = clock or time.time
        self._ttl_seconds = ttl_seconds
        self._capacity = capacity
        self._challenges: dict[str, StepUpChallenge] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        owner_sub: str,
        session_id: str,
        plan_id: str,
        action_digest: str,
        risk_class: str,
    ) -> StepUpChallengeReceipt:
        """Create a short-lived challenge only for backend-classified high risk."""
        if not self._valid_identity(owner_sub, session_id):
            raise ValueError("authenticated owner and session are required")
        if not isinstance(plan_id, str) or not PLAN_ID_PATTERN.fullmatch(plan_id):
            raise ValueError("invalid plan identifier")
        if not isinstance(action_digest, str) or not ACTION_DIGEST_PATTERN.fullmatch(action_digest):
            raise ValueError("invalid action digest")
        if risk_class != "high":
            raise ValueError("step-up challenge is required only for high-risk actions")

        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            raise RuntimeError("system clock is invalid")
        with self._lock:
            self._remove_expired(now)
            if len(self._challenges) >= self._capacity:
                raise RuntimeError("active challenge capacity reached")
            challenge_id = secrets.token_hex(16)
            challenge = StepUpChallenge(
                challenge_id=challenge_id,
                owner_sub=owner_sub,
                session_id=session_id,
                plan_id=plan_id,
                action_digest=action_digest,
                risk_class=risk_class,
                created_at=float(now),
                expires_at=float(now) + self._ttl_seconds,
            )
            self._challenges[challenge_id] = challenge
            return StepUpChallengeReceipt(
                challenge_id=challenge_id,
                expires_at=challenge.expires_at,
                plan_id=challenge.plan_id,
                action_digest=challenge.action_digest,
            )

    def verify_and_consume(
        self,
        *,
        challenge_id: str,
        owner_sub: str,
        session_id: str,
        plan_id: str,
        action_digest: str,
        risk_class: str,
        secret: str,
        code: str,
    ) -> bool:
        """Consume a challenge only when identity, session, action and TOTP match."""
        if not self._valid_identity(owner_sub, session_id):
            return False
        now = self._clock()
        if (
            isinstance(now, bool)
            or not isinstance(now, (int, float))
            or not math.isfinite(now)
            or now < 0
        ):
            return False

        with self._lock:
            challenge = self._challenges.get(challenge_id)
            if challenge is None or challenge.status != "active":
                return False
            if now >= challenge.expires_at:
                self._replace(challenge, status="expired")
                return False
            if challenge.owner_sub != owner_sub or challenge.session_id != session_id:
                return False

            # A changed plan, digest or server-derived risk invalidates this
            # challenge; it cannot be repurposed for a different action.
            if (
                challenge.plan_id != plan_id
                or challenge.action_digest != action_digest
                or challenge.risk_class != risk_class
            ):
                self._replace(challenge, status="invalidated")
                return False

            if challenge.failed_attempts >= MAX_FAILED_ATTEMPTS:
                self._replace(challenge, status="locked")
                return False

            accepted = self._replay_guard.verify_and_consume(
                owner_key=owner_sub,
                secret=secret,
                code=code,
                timestamp=float(now),
            )
            if not accepted:
                attempts = challenge.failed_attempts + 1
                status: ChallengeStatus = (
                    "locked" if attempts >= MAX_FAILED_ATTEMPTS else "active"
                )
                self._replace(challenge, failed_attempts=attempts, status=status)
                return False

            self._replace(challenge, status="consumed")
            return True

    def get(self, challenge_id: str) -> StepUpChallenge | None:
        """Return an internal immutable snapshot for trusted service/tests only."""
        with self._lock:
            return self._challenges.get(challenge_id)

    def _replace(
        self,
        challenge: StepUpChallenge,
        *,
        failed_attempts: int | None = None,
        status: ChallengeStatus | None = None,
    ) -> None:
        self._challenges[challenge.challenge_id] = StepUpChallenge(
            challenge_id=challenge.challenge_id,
            owner_sub=challenge.owner_sub,
            session_id=challenge.session_id,
            plan_id=challenge.plan_id,
            action_digest=challenge.action_digest,
            risk_class=challenge.risk_class,
            created_at=challenge.created_at,
            expires_at=challenge.expires_at,
            failed_attempts=(
                challenge.failed_attempts if failed_attempts is None else failed_attempts
            ),
            status=challenge.status if status is None else status,
        )

    def _remove_expired(self, now: float) -> None:
        expired_ids = [
            challenge_id
            for challenge_id, challenge in self._challenges.items()
            if now >= challenge.expires_at
        ]
        for challenge_id in expired_ids:
            self._challenges.pop(challenge_id, None)

    @staticmethod
    def _valid_identity(owner_sub: str, session_id: str) -> bool:
        return (
            isinstance(owner_sub, str)
            and 1 <= len(owner_sub) <= 256
            and isinstance(session_id, str)
            and 1 <= len(session_id) <= 128
        )
