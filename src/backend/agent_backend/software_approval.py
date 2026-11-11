"""Immutable, digest-bound software install proposal contract.

This module defines the data boundary between trusted software discovery and
exact-action approval. It does not discover packages, authenticate publishers,
or execute installers. Only a trusted discovery service may construct evidence
after independently validating its source and installer metadata.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VerifiedPackageEvidence(BaseModel):
    """Immutable snapshot of the package facts shown to the user for approval."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    evidence_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    package_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
    publisher: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    source: Literal["winget"]
    installer_url: str = Field(min_length=8, max_length=2048)
    installer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    architecture: Literal["x86", "x64", "arm64"]
    scope: Literal["user"]
    signature_subject: str = Field(min_length=1, max_length=300)
    verified_at: datetime
    expires_at: datetime

    @field_validator("publisher", "version", "signature_subject")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("installer_url")
    @classmethod
    def require_https_installer_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("installer URL must be an absolute HTTPS URL without credentials or fragment")
        return value

    @model_validator(mode="after")
    def validate_evidence_window(self) -> VerifiedPackageEvidence:
        if (
            self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise ValueError("evidence timestamps must be timezone-aware")
        if self.expires_at <= self.verified_at:
            raise ValueError("evidence expiry must be after verification")
        if (self.expires_at - self.verified_at).total_seconds() > 900:
            raise ValueError("evidence validity must not exceed 15 minutes")
        return self


class InstallApprovalBinding(BaseModel):
    """The exact plan plus immutable package evidence presented for approval."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["p6-603-install-approval-v1"] = "p6-603-install-approval-v1"
    action: Literal["software.install"] = "software.install"
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence: VerifiedPackageEvidence
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_approval_digest(self) -> InstallApprovalBinding:
        if self.approval_digest != digest_install_approval(
            plan_digest=self.plan_digest,
            evidence=self.evidence,
        ):
            raise ValueError("approval digest does not match the exact install proposal")
        return self

    def ensure_fresh(self, *, now: datetime) -> None:
        """Fail closed when package evidence is not current at approval time."""
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("approval time must be timezone-aware")
        if now < self.evidence.verified_at or now >= self.evidence.expires_at:
            raise ValueError("verified package evidence is not current")


def digest_install_approval(
    *,
    plan_digest: str,
    evidence: VerifiedPackageEvidence,
) -> str:
    """Hash every material field so any proposal substitution changes approval."""
    if not isinstance(evidence, VerifiedPackageEvidence):
        raise TypeError("evidence must be a validated VerifiedPackageEvidence")
    if not isinstance(plan_digest, str) or len(plan_digest) != 64:
        raise ValueError("plan digest must be a SHA-256 hex digest")
    if any(char not in "0123456789abcdef" for char in plan_digest):
        raise ValueError("plan digest must be a lowercase SHA-256 hex digest")
    payload = {
        "schema_version": "p6-603-install-approval-v1",
        "action": "software.install",
        "plan_digest": plan_digest,
        "evidence": evidence.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_install_approval_binding(
    *,
    plan_digest: str,
    evidence: VerifiedPackageEvidence,
) -> InstallApprovalBinding:
    """Build the immutable binding consumed later by step-up approval."""
    return InstallApprovalBinding(
        plan_digest=plan_digest,
        evidence=evidence,
        approval_digest=digest_install_approval(
            plan_digest=plan_digest,
            evidence=evidence,
        ),
    )
