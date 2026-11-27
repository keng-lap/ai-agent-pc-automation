"""Backend-only registry for immutable, short-lived installer evidence.

All packages use the same installer SHA-256 verification policy. Authenticode
checks signature integrity only; signer identity is never compared with Publisher.
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from pydantic import ValidationError

from agent_backend.software_approval import (
    InstallApprovalBinding,
    VerifiedPackageEvidence,
    build_install_approval_binding,
)
from agent_backend.software_discovery import InstallerCandidate
from agent_backend.software_staging import StagedInstaller

EVIDENCE_TTL = timedelta(minutes=15)
MAX_EVIDENCE = 128


class EvidenceNotFound(LookupError):
    """Evidence is unknown, expired, or no longer available."""


class EvidenceRejected(ValueError):
    """Trusted discovery/staging facts failed policy with a safe diagnostic reason."""

    _REASONS: ClassVar[dict[str, tuple[str, str]]] = {
        "candidate and staged proof must be backend model instances": ("invalid_evidence_input", "Candidate or staged proof was not created by the backend trust pipeline."),
        "DBeaver official release evidence is not verified": ("official_release_evidence_unverified", "Official DBeaver release version, URL, and digest were not verified."),
        "unchecked publisher candidate contained unexpected vendor release claims": ("unexpected_publisher_claims", "Unverified candidate contained unexpected official publisher claims."),
        "verified vendor release did not match the exact manifest candidate": ("official_release_manifest_mismatch", "Official release evidence did not match the exact WinGet manifest candidate."),
        "package publisher source check did not pass": ("publisher_source_check_failed", "Official publisher source verification did not pass."),
        "staged installer does not prove the exact candidate and signer": ("staged_installer_evidence_mismatch", "Staged file hash, version, architecture, or Authenticode proof did not match the selected candidate."),
        "staged installer release origin does not match the candidate": ("official_release_origin_mismatch", "Staged installer release origin did not match the verified candidate."),
        "discovery or staging timestamp is invalid": ("invalid_evidence_timestamp", "Discovery or staging timestamp could not be parsed."),
        "discovery and staging timestamps must be timezone-aware": ("invalid_evidence_timestamp", "Discovery and staging timestamps were not timezone-aware."),
        "discovery or staged installer proof is not current": ("installer_evidence_expired", "Discovery or staged installer evidence exceeded its validity window."),
        "evidence registry capacity reached": ("evidence_capacity_reached", "Verified evidence registry reached its capacity limit."),
        "evidence identifier collision": ("evidence_id_collision", "Evidence identifier collision prevented registration."),
    }

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.failure_code, self.failure_reason = self._REASONS.get(
            message,
            ("installer_evidence_rejected", "Installer evidence did not satisfy the verification policy."),
        )


class SoftwareEvidenceRegistry:
    """Bounded process-local evidence registry; never trusts client-supplied facts."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        capacity: int = MAX_EVIDENCE,
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_EVIDENCE:
            raise ValueError("evidence capacity must be between 1 and 128")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._capacity = capacity
        self._entries: dict[str, VerifiedPackageEvidence] = {}
        self._lock = threading.RLock()

    def register_staged_candidate(
        self,
        *,
        candidate: InstallerCandidate,
        staged: StagedInstaller,
    ) -> VerifiedPackageEvidence:
        """Mint evidence only from matching backend candidate and staged-file proof."""
        if not isinstance(candidate, InstallerCandidate) or not isinstance(staged, StagedInstaller):
            raise EvidenceRejected("candidate and staged proof must be backend model instances")
        is_dbeaver = candidate.package_id == "DBeaver.DBeaver.Community"
        if candidate.status != "CONDITIONAL":
            raise EvidenceRejected("package discovery candidate is not conditional")
        if is_dbeaver:
            if (
                candidate.publisher_verification != "VERIFIED"
                or candidate.official_version != candidate.version
                or not candidate.official_release_url
                or candidate.official_asset_sha256 != candidate.installer_sha256
            ):
                raise EvidenceRejected("DBeaver official release evidence is not verified")
        elif candidate.publisher_verification == "NOT_CHECKED":
            if any((
                candidate.official_version is not None,
                candidate.official_release_url is not None,
                candidate.official_asset_sha256 is not None,
                candidate.official_asset_id is not None,
            )):
                raise EvidenceRejected("unchecked publisher candidate contained unexpected vendor release claims")
        elif candidate.publisher_verification == "VERIFIED":
            if (
                candidate.official_version != candidate.version
                or not candidate.official_release_url
                or candidate.official_asset_sha256 != candidate.installer_sha256
            ):
                raise EvidenceRejected("verified vendor release did not match the exact manifest candidate")
        else:
            raise EvidenceRejected("package publisher source check did not pass")
        if (
            staged.package_id != candidate.package_id
            or staged.version != candidate.version
            or staged.architecture != candidate.architecture
            or staged.sha256 != candidate.installer_sha256
            or staged.authenticode_valid is not True
        ):
            raise EvidenceRejected("staged installer does not prove the exact candidate and signer")
        if staged.official_release_url != candidate.official_release_url:
            raise EvidenceRejected("staged installer release origin does not match the candidate")

        try:
            verified_at = datetime.fromisoformat(staged.staged_at)
            candidate_checked_at = datetime.fromisoformat(candidate.checked_at)
        except (TypeError, ValueError):
            raise EvidenceRejected("discovery or staging timestamp is invalid") from None
        if (
            verified_at.tzinfo is None or verified_at.utcoffset() is None
            or candidate_checked_at.tzinfo is None or candidate_checked_at.utcoffset() is None
        ):
            raise EvidenceRejected("discovery and staging timestamps must be timezone-aware")

        now = self._now()
        if (
            verified_at > now
            or candidate_checked_at > now
            or now - verified_at > EVIDENCE_TTL
            or now - candidate_checked_at > EVIDENCE_TTL
        ):
            raise EvidenceRejected("discovery or staged installer proof is not current")

        try:
            evidence = VerifiedPackageEvidence(
                evidence_id=secrets.token_hex(16),
                package_id=candidate.package_id,
                package_name=candidate.package_name,
                publisher=candidate.publisher,
                version=candidate.version,
                source="winget",
                installer_type=candidate.installer_type,
                installer_silent_switch=candidate.installer_silent_switch,
                installer_url=candidate.installer_url,
                official_release_url=candidate.official_release_url,
                manifest_source_url=candidate.manifest_source_url,
                repository_commit=candidate.repository_commit,
                installer_sha256=candidate.installer_sha256,
                manifest_sha256=candidate.manifest_sha256,
                architecture=candidate.architecture,
                scope=candidate.scope,
                verified_at=verified_at,
                expires_at=min(verified_at + EVIDENCE_TTL, now + EVIDENCE_TTL),
            )
        except ValidationError as exc:
            raise EvidenceRejected("installer evidence contains invalid fields") from exc
        with self._lock:
            self._prune(now)
            if len(self._entries) >= self._capacity:
                raise EvidenceRejected("evidence registry capacity reached")
            if evidence.evidence_id in self._entries:
                raise EvidenceRejected("evidence identifier collision")
            self._entries[evidence.evidence_id] = evidence
        return evidence

    def get(self, evidence_id: str) -> VerifiedPackageEvidence:
        """Resolve one opaque evidence ID and re-check freshness."""
        if not isinstance(evidence_id, str) or len(evidence_id) != 32:
            raise EvidenceNotFound("evidence not found")
        now = self._now()
        with self._lock:
            evidence = self._entries.get(evidence_id)
            if evidence is None:
                raise EvidenceNotFound("evidence not found")
            try:
                binding = build_install_approval_binding(
                    plan_digest="0" * 64,
                    evidence=evidence,
                )
                binding.ensure_fresh(now=now)
            except ValueError:
                self._entries.pop(evidence_id, None)
                raise EvidenceNotFound("evidence not found") from None
            return evidence

    def bind_to_plan(self, *, evidence_id: str, plan_digest: str) -> InstallApprovalBinding:
        """Create a fresh exact-action binding for a server-owned plan digest."""
        evidence = self.get(evidence_id)
        try:
            binding = build_install_approval_binding(
                plan_digest=plan_digest,
                evidence=evidence,
            )
            binding.ensure_fresh(now=self._now())
        except (TypeError, ValueError):
            raise EvidenceRejected("evidence cannot be bound to this plan") from None
        return binding

    def revoke(self, evidence_id: str) -> None:
        """Revoke evidence after a source refresh or explicit invalidation."""
        with self._lock:
            self._entries.pop(evidence_id, None)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("evidence registry clock must be timezone-aware")
        return now.astimezone(UTC)

    def _prune(self, now: datetime) -> None:
        expired = [
            key for key, value in self._entries.items()
            if now >= value.expires_at
        ]
        for key in expired:
            self._entries.pop(key, None)



software_evidence_registry = SoftwareEvidenceRegistry()
