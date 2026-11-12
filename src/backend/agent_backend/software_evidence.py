"""Backend-only registry for immutable, short-lived installer evidence.

No HTTP endpoint accepts evidence fields. Only the trusted staging path may
register a candidate, and registration fails closed unless the staged binary
has a verified Authenticode signer subject matching the expected publisher.
"""

from __future__ import annotations

import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Callable

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
    """The trusted discovery/staging facts do not satisfy evidence policy."""


class SoftwareEvidenceRegistry:
    """Bounded process-local evidence registry; never trusts client-supplied facts."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        capacity: int = MAX_EVIDENCE,
        signer_subject_verifier: Callable[[InstallerCandidate, str], bool] | None = None,
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_EVIDENCE:
            raise ValueError("evidence capacity must be between 1 and 128")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._capacity = capacity
        # No publisher signer trust anchors are configured by default.
        # Until an independently reviewed anchor is supplied, registration denies.
        self._signer_subject_verifier = signer_subject_verifier or (lambda _candidate, _subject: False)
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
        if (
            candidate.publisher_verification != "VERIFIED"
            or candidate.status != "CONDITIONAL"
            or candidate.official_version != candidate.version
            or not candidate.official_release_url
            or candidate.official_asset_sha256 != candidate.installer_sha256
        ):
            raise EvidenceRejected("publisher release evidence is not verified")
        if (
            staged.package_id != candidate.package_id
            or staged.version != candidate.version
            or staged.architecture != candidate.architecture
            or staged.sha256 != candidate.installer_sha256
            or staged.authenticode_valid is not True
            or not staged.signature_subject
        ):
            raise EvidenceRejected("staged installer does not prove the exact candidate and signer")
        if staged.official_release_url != candidate.official_release_url:
            raise EvidenceRejected("staged installer release origin does not match the candidate")
        try:
            signer_matches = self._signer_subject_verifier(candidate, staged.signature_subject)
        except Exception:
            signer_matches = False
        if signer_matches is not True:
            raise EvidenceRejected("Authenticode signer does not match a backend-owned publisher trust anchor")

        try:
            verified_at = datetime.fromisoformat(staged.staged_at)
        except (TypeError, ValueError):
            raise EvidenceRejected("staging timestamp is invalid") from None
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise EvidenceRejected("staging timestamp must be timezone-aware")

        now = self._now()
        if verified_at > now or now - verified_at > EVIDENCE_TTL:
            raise EvidenceRejected("staged installer proof is not current")

        evidence = VerifiedPackageEvidence(
            evidence_id=secrets.token_hex(16),
            package_id=candidate.package_id,
            publisher=candidate.publisher,
            version=candidate.version,
            source="winget",
            installer_url=candidate.installer_url,
            installer_sha256=candidate.installer_sha256,
            manifest_sha256=candidate.manifest_sha256,
            architecture=candidate.architecture,
            scope=candidate.scope,
            signature_subject=staged.signature_subject,
            verified_at=verified_at,
            expires_at=min(verified_at + EVIDENCE_TTL, now + EVIDENCE_TTL),
        )
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
