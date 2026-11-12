"""Tests for backend-only verified software evidence registry."""

from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.software_discovery import InstallerCandidate
from agent_backend.software_evidence import (
    EvidenceNotFound,
    EvidenceRejected,
    SoftwareEvidenceRegistry,
)
from agent_backend.software_staging import StagedInstaller

NOW = datetime(2026, 11, 12, tzinfo=UTC)
PLAN_DIGEST = "d" * 64


def make_registry(*, clock=lambda: NOW) -> SoftwareEvidenceRegistry:
    return SoftwareEvidenceRegistry(
        clock=clock,
        signer_subject_verifier=lambda item, subject: (
            item.package_id == "DBeaver.DBeaver.Community"
            and subject == "CN=DBeaver Corporation"
        ),
    )


def candidate() -> InstallerCandidate:
    return InstallerCandidate(
        package_id="DBeaver.DBeaver.Community",
        package_name="DBeaver Community Edition",
        publisher="DBeaver Corp",
        version="26.2.4",
        architecture="x64",
        scope="user",
        installer_type="exe",
        installer_url="https://github.com/dbeaver/dbeaver/releases/download/26.2.4/dbeaver-ce-26.2.4-windows-x86_64.exe",
        installer_domain="github.com",
        installer_sha256="a" * 64,
        manifest_sha256="b" * 64,
        repository_commit="c" * 40,
        manifest_source_url="https://github.com/microsoft/winget-pkgs/tree/c",
        checked_at=NOW.isoformat(),
        publisher_verification="VERIFIED",
        official_version="26.2.4",
        official_release_url="https://github.com/dbeaver/dbeaver/releases/tag/26.2.4",
        official_asset_sha256="a" * 64,
        limitations=("installer_authenticode_signature_not_yet_verified",),
    )


def staged(**overrides) -> StagedInstaller:
    values = {
        "package_id": "DBeaver.DBeaver.Community",
        "version": "26.2.4",
        "architecture": "x64",
        "file_path": "C:/staging/installer.exe",
        "file_size": 1234,
        "sha256": "a" * 64,
        "authenticode_valid": True,
        "signature_subject": "CN=DBeaver Corporation",
        "official_release_url": "https://github.com/dbeaver/dbeaver/releases/tag/26.2.4",
        "staged_at": NOW.isoformat(),
    }
    values.update(overrides)
    return StagedInstaller(**values)


def test_registry_mints_evidence_only_from_exact_candidate_and_signer_proof():
    registry = make_registry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(
        candidate=candidate(),
        staged=staged(),
    )

    assert evidence.package_id == "DBeaver.DBeaver.Community"
    assert evidence.version == "26.2.4"
    assert evidence.installer_sha256 == "a" * 64
    assert evidence.signature_subject == "CN=DBeaver Corporation"
    assert registry.get(evidence.evidence_id) == evidence

    binding = registry.bind_to_plan(
        evidence_id=evidence.evidence_id,
        plan_digest=PLAN_DIGEST,
    )
    assert binding.plan_digest == PLAN_DIGEST
    assert binding.evidence == evidence
    assert len(binding.approval_digest) == 64


@pytest.mark.parametrize(
    "candidate_overrides,staged_overrides",
    [
        ({"publisher_verification": "MISMATCH"}, {}),
        ({"official_version": "26.2.3"}, {}),
        ({"installer_sha256": "e" * 64}, {}),
        ({}, {"package_id": "Other.Package"}),
        ({}, {"version": "26.2.3"}),
        ({}, {"architecture": "arm64"}),
        ({}, {"sha256": "e" * 64}),
        ({}, {"signature_subject": None}),
        ({}, {"official_release_url": "https://evil.example/release"}),
    ],
)
def test_registry_rejects_mismatched_or_incomplete_proof(candidate_overrides, staged_overrides):
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    with pytest.raises(EvidenceRejected):
        registry.register_staged_candidate(
            candidate=candidate().model_copy(update=candidate_overrides),
            staged=staged(**staged_overrides),
        )


def test_registry_rejects_stale_or_future_staging_proof():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    stale = staged(staged_at=(NOW - timedelta(minutes=16)).isoformat())
    future = staged(staged_at=(NOW + timedelta(seconds=1)).isoformat())

    with pytest.raises(EvidenceRejected, match="not current"):
        registry.register_staged_candidate(candidate=candidate(), staged=stale)
    with pytest.raises(EvidenceRejected, match="not current"):
        registry.register_staged_candidate(candidate=candidate(), staged=future)


def test_evidence_expires_and_is_removed_from_registry():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    later = make_registry(clock=lambda: NOW + timedelta(minutes=16))
    later._entries[evidence.evidence_id] = evidence

    with pytest.raises(EvidenceNotFound):
        later.get(evidence.evidence_id)


def test_binding_is_digest_specific_and_revocable():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    first = registry.bind_to_plan(evidence_id=evidence.evidence_id, plan_digest=PLAN_DIGEST)
    second = registry.bind_to_plan(evidence_id=evidence.evidence_id, plan_digest="e" * 64)

    assert first.approval_digest != second.approval_digest
    registry.revoke(evidence.evidence_id)
    with pytest.raises(EvidenceNotFound):
        registry.get(evidence.evidence_id)


def test_default_registry_rejects_signer_without_configured_trust_anchor():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    with pytest.raises(EvidenceRejected, match="trust anchor"):
        registry.register_staged_candidate(candidate=candidate(), staged=staged())
