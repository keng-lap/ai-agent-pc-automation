"""Immutable, process-local P1 dry-run plan contract (P5-512).

This module creates reports only. It has no OS, network, package-manager, or
machine-inspection capability. Plan references are intentionally ephemeral.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlanToolId = Literal["software.install", "software.remove"]
PlanItemStatus = Literal["PLANNED", "NEEDS_CLARIFICATION", "BLOCKED", "UNSUPPORTED"]

PLAN_SCHEMA_VERSION = "p5-512-plan-v1"
TOOL_CONTRACT_VERSION = "1"
PLAN_TTL = timedelta(minutes=10)
MAX_PLAN_ITEMS = 50
MAX_ACTIVE_PLANS = 128


class ProgramPlan(BaseModel):
    """One explicit program/action in the immutable dry-run report."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        str_strip_whitespace=True,
    )

    order: int = Field(ge=1, le=MAX_PLAN_ITEMS)
    program: str = Field(min_length=1, max_length=120)
    version: str = Field(default="Not specified", min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=240)
    reason: str = Field(min_length=1, max_length=500)
    source: str = Field(default="Not checked", min_length=1, max_length=160)
    source_verification: Literal["NOT_CHECKED"] = "NOT_CHECKED"
    dependencies: tuple[str, ...] = Field(default=(), max_length=20)
    dependencies_verification: Literal["NOT_CHECKED"] = "NOT_CHECKED"
    disk_space_estimate: str | None = Field(default=None, max_length=80)
    impact: str = Field(default="Unknown / not checked", min_length=1, max_length=240)
    status: PlanItemStatus

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() or len(item) > 120 for item in value):
            raise ValueError("dependencies must contain bounded non-empty names")
        if len({item.casefold() for item in value}) != len(value):
            raise ValueError("dependencies must be unique")
        return value


class DryRunPlan(BaseModel):
    """Server-created plan envelope; never an execution or approval grant."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["p5-512-plan-v1"] = PLAN_SCHEMA_VERSION
    plan_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    tool_id: PlanToolId
    tool_contract_version: Literal["1"] = TOOL_CONTRACT_VERSION
    risk_class: Literal["R1"] = "R1"
    required_permission: Literal["P1"] = "P1"
    mode: Literal["dry_run"] = "dry_run"
    live_checks_performed: Literal[False] = False
    report_notice: Literal["DRY_RUN_ONLY_NO_CHANGES_MADE"] = "DRY_RUN_ONLY_NO_CHANGES_MADE"
    programs: tuple[ProgramPlan, ...] = Field(min_length=1, max_length=MAX_PLAN_ITEMS)
    created_at: datetime
    expires_at: datetime
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_envelope(self) -> "DryRunPlan":
        if not _is_utc(self.created_at) or not _is_utc(self.expires_at):
            raise ValueError("plan timestamps must be timezone-aware UTC values")
        if self.expires_at != self.created_at + PLAN_TTL:
            raise ValueError("plan expiry must be exactly ten minutes after creation")
        orders = tuple(item.order for item in self.programs)
        if orders != tuple(range(1, len(self.programs) + 1)):
            raise ValueError("program order must be contiguous and start at one")
        names = tuple(item.program.casefold() for item in self.programs)
        if len(set(names)) != len(names):
            raise ValueError("program names must be unique")
        expected_digest = _digest_for(
            tool_id=self.tool_id,
            tool_contract_version=self.tool_contract_version,
            programs=self.programs,
        )
        if self.plan_digest != expected_digest:
            raise ValueError("plan digest does not match the immutable plan content")
        return self


class PlanNotFoundError(LookupError):
    """The process-local plan reference does not exist."""


class PlanExpiredError(LookupError):
    """The process-local plan reference has expired."""


class PlanIntegrityError(RuntimeError):
    """A stored plan failed its integrity check."""


class PlanCapacityError(RuntimeError):
    """The bounded in-memory plan store is full."""


class PlanClockError(RuntimeError):
    """The backend clock became invalid or moved backwards."""


def _is_utc(value: datetime) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _canonical_identity(
    *,
    tool_id: PlanToolId,
    tool_contract_version: str,
    programs: tuple[ProgramPlan, ...],
) -> str:
    """Serialize every material per-program field deterministically."""
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "tool_id": tool_id,
        "tool_contract_version": tool_contract_version,
        "risk_class": "R1",
        "required_permission": "P1",
        "mode": "dry_run",
        "live_checks_performed": False,
        "report_notice": "DRY_RUN_ONLY_NO_CHANGES_MADE",
        "programs": [item.model_dump(mode="json") for item in programs],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest_for(
    *,
    tool_id: PlanToolId,
    tool_contract_version: str,
    programs: tuple[ProgramPlan, ...],
) -> str:
    canonical = _canonical_identity(
        tool_id=tool_id,
        tool_contract_version=tool_contract_version,
        programs=programs,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_dry_run_plan(
    tool_id: PlanToolId,
    programs: Sequence[ProgramPlan],
    *,
    now: datetime | None = None,
) -> DryRunPlan:
    """Build a new server-identified plan from validated, explicit program items."""
    created_at = now or datetime.now(timezone.utc)
    if not _is_utc(created_at):
        raise ValueError("creation time must be timezone-aware UTC")
    items = tuple(programs)
    if any(not isinstance(item, ProgramPlan) for item in items):
        raise TypeError("programs must contain validated ProgramPlan instances")
    if not items or len(items) > MAX_PLAN_ITEMS:
        raise ValueError("a plan must contain between 1 and 50 program items")
    digest = _digest_for(
        tool_id=tool_id,
        tool_contract_version=TOOL_CONTRACT_VERSION,
        programs=items,
    )
    return DryRunPlan(
        plan_id=uuid4().hex,
        tool_id=tool_id,
        programs=items,
        created_at=created_at,
        expires_at=created_at + PLAN_TTL,
        plan_digest=digest,
    )


class PlanStore:
    """Thread-safe, bounded, process-local plan references; never persisted."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._plans: dict[str, DryRunPlan] = {}
        self._last_seen_at: datetime | None = None
        self._clock_invalid = False
        self._lock = threading.RLock()

    def create(
        self,
        tool_id: PlanToolId,
        programs: Sequence[ProgramPlan],
    ) -> DryRunPlan:
        with self._lock:
            now = self._clock()
            self._observe_clock(now)
            self._remove_expired(now)
            if len(self._plans) >= MAX_ACTIVE_PLANS:
                raise PlanCapacityError("active plan capacity reached")
            plan = create_dry_run_plan(tool_id, programs, now=now)
            self._plans[plan.plan_id] = plan
            return plan

    def get(self, plan_id: str) -> DryRunPlan:
        with self._lock:
            now = self._clock()
            self._observe_clock(now)
            plan = self._plans.get(plan_id)
            if plan is None:
                raise PlanNotFoundError("plan reference not found")
            if now >= plan.expires_at:
                self._plans.pop(plan_id, None)
                raise PlanExpiredError("plan reference expired")
            expected = _digest_for(
                tool_id=plan.tool_id,
                tool_contract_version=plan.tool_contract_version,
                programs=plan.programs,
            )
            if expected != plan.plan_digest:
                self._plans.pop(plan_id, None)
                raise PlanIntegrityError("stored plan integrity check failed")
            return plan

    def _observe_clock(self, now: datetime) -> None:
        if self._clock_invalid:
            raise PlanClockError("plan store clock is invalid; restart is required")
        if not _is_utc(now) or (
            self._last_seen_at is not None and now < self._last_seen_at
        ):
            self._plans.clear()
            self._clock_invalid = True
            raise PlanClockError("plan store clock is invalid or moved backwards")
        self._last_seen_at = now

    def _remove_expired(self, now: datetime) -> None:
        expired = [
            plan_id for plan_id, plan in self._plans.items() if now >= plan.expires_at
        ]
        for plan_id in expired:
            self._plans.pop(plan_id, None)
