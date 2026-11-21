"""Immutable real-install proposal contract, separate from legacy preview plans."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_backend.software_approval import VerifiedPackageEvidence

INSTALL_PLAN_TTL = timedelta(minutes=10)
MAX_ACTIVE_INSTALL_PLANS = 128


def _canonical_payload(
    *,
    evidence_id: str,
    package_id: str,
    package_name: str,
    publisher: str,
    version: str,
    architecture: str,
    scope: str,
    created_at: datetime,
    expires_at: datetime,
) -> str:
    return json.dumps(
        {
            "schema_version": "p6-609-install-plan-v1",
            "action": "software.install",
            "evidence_id": evidence_id,
            "package_id": package_id,
            "package_name": package_name,
            "publisher": publisher,
            "version": version,
            "architecture": architecture,
            "scope": scope,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(**values: object) -> str:
    return hashlib.sha256(_canonical_payload(**values).encode("utf-8")).hexdigest()


class SoftwareInstallPlan(BaseModel):
    """Exact package proposal; unlike a preview, it authorizes no action by itself."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["p6-609-install-plan-v1"] = "p6-609-install-plan-v1"
    plan_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    action: Literal["software.install"] = "software.install"
    evidence_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    package_id: str = Field(min_length=1, max_length=160)
    package_name: str = Field(min_length=1, max_length=200)
    publisher: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    architecture: Literal["x86", "x64", "arm64"]
    scope: Literal["user"] = "user"
    created_at: datetime
    expires_at: datetime
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_integrity(self) -> SoftwareInstallPlan:
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.created_at.utcoffset() != timedelta(0)
            or self.expires_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("install plan timestamps must be UTC")
        if self.expires_at != self.created_at + INSTALL_PLAN_TTL:
            raise ValueError("install plan expiry must be exactly ten minutes after creation")
        expected = _digest(
            evidence_id=self.evidence_id,
            package_id=self.package_id,
            package_name=self.package_name,
            publisher=self.publisher,
            version=self.version,
            architecture=self.architecture,
            scope=self.scope,
            created_at=self.created_at,
            expires_at=self.expires_at,
        )
        if self.plan_digest != expected:
            raise ValueError("install plan digest does not match its immutable content")
        return self


class InstallPlanNotFound(LookupError):
    """The opaque install proposal is unknown or expired."""


class InstallPlanCapacityError(RuntimeError):
    """The bounded active install-plan registry is full."""


class SoftwareInstallPlanStore:
    """Short-lived process-local proposals minted only from backend evidence."""

    def __init__(self, *, clock=None, capacity: int = MAX_ACTIVE_INSTALL_PLANS) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_ACTIVE_INSTALL_PLANS:
            raise ValueError("install plan capacity must be between 1 and 128")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._capacity = capacity
        self._plans: dict[str, SoftwareInstallPlan] = {}
        self._lock = threading.RLock()

    def create(self, evidence: VerifiedPackageEvidence) -> SoftwareInstallPlan:
        if not isinstance(evidence, VerifiedPackageEvidence):
            raise TypeError("install plan requires backend-verified package evidence")
        now = self._now()
        evidence.ensure_fresh(now=now)
        expires_at = now + INSTALL_PLAN_TTL
        values = {
            "evidence_id": evidence.evidence_id,
            "package_id": evidence.package_id,
            "package_name": evidence.package_name,
            "publisher": evidence.publisher,
            "version": evidence.version,
            "architecture": evidence.architecture,
            "scope": evidence.scope,
            "created_at": now,
            "expires_at": expires_at,
        }
        plan = SoftwareInstallPlan(
            plan_id=uuid4().hex,
            plan_digest=_digest(**values),
            **values,
        )
        with self._lock:
            self._prune(now)
            if len(self._plans) >= self._capacity:
                raise InstallPlanCapacityError("active install plan capacity reached")
            self._plans[plan.plan_id] = plan
        return plan

    def get(self, plan_id: str) -> SoftwareInstallPlan:
        if not isinstance(plan_id, str) or len(plan_id) != 32:
            raise InstallPlanNotFound("install plan not found")
        now = self._now()
        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                raise InstallPlanNotFound("install plan not found")
            if now >= plan.expires_at:
                self._plans.pop(plan_id, None)
                raise InstallPlanNotFound("install plan not found")
            try:
                SoftwareInstallPlan.model_validate(plan.model_dump())
            except ValueError:
                self._plans.pop(plan_id, None)
                raise InstallPlanNotFound("install plan not found") from None
            return plan

    def _now(self) -> datetime:
        now = self._clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() != timedelta(0)
        ):
            raise RuntimeError("install plan clock must return UTC-aware timestamps")
        return now

    def _prune(self, now: datetime) -> None:
        expired = [key for key, plan in self._plans.items() if now >= plan.expires_at]
        for key in expired:
            self._plans.pop(key, None)


software_install_plan_store = SoftwareInstallPlanStore()
