"""Tests for backend-only verified software evidence registry."""

from datetime import UTC, datetime, timedelta

import pytest

from agent_backend.software_approval import build_install_approval_binding
from agent_backend.software_discovery import InstallerCandidate
from agent_backend.software_evidence import (
    EvidenceNotFound,
    EvidenceRejected,
    SoftwareEvidenceRegistry,
    signer_subject_matches_publisher,
)
from agent_backend.software_staging import StagedInstaller

NOW = datetime(2026, 11, 12, tzinfo=UTC)
PLAN_DIGEST = "d" * 64


def make_registry(*, clock=lambda: NOW) -> SoftwareEvidenceRegistry:
    return SoftwareEvidenceRegistry(clock=clock)


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
        official_asset_id=12345,
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
        "signature_sha256": "d" * 64,
        "official_release_url": "https://github.com/dbeaver/dbeaver/releases/tag/26.2.4",
        "staged_at": NOW.isoformat(),
    }
    values.update(overrides)
    return StagedInstaller(**values)



@pytest.mark.parametrize(
    "subject,publisher,expected",
    [
        ("CN=Acme Software, O=Acme Corporation, C=US", "Acme Corp", True),
        ('C=US, S=California, L=San Francisco, O="GitHub, Inc.", CN="GitHub, Inc."', "GitHub, Inc.", True),
        ("CN=Acme, O=Acme\\, Incorporated, C=US", "Acme Inc", True),
        ("CN=Acme Inc, O=Evil Corp, C=US", "Acme Inc", False),
        ("CN=Acme Inc, O=Acme Inc, O=Other Inc", "Acme Inc", False),
        ("CN=Acme Inc, C=US", "Acme Inc", True),
        ("CN=Acme Inc, O=  , C=US", "Acme Inc", False),
    ],
)
def test_signer_subject_publisher_matching_is_exact_and_fail_closed(subject, publisher, expected):
    assert signer_subject_matches_publisher(subject, publisher) is expected


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
    assert evidence.signature_sha256 == "d" * 64
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
        ({}, {"signature_sha256": None}),
        ({}, {"official_release_url": "https://evil.example/release"}),
    ],
)
def test_registry_rejects_mismatched_or_incomplete_proof(candidate_overrides, staged_overrides):
    registry = make_registry(clock=lambda: NOW)
    with pytest.raises(EvidenceRejected):
        registry.register_staged_candidate(
            candidate=candidate().model_copy(update=candidate_overrides),
            staged=staged(**staged_overrides),
        )


def test_registry_rejects_stale_or_future_staging_proof():
    registry = make_registry(clock=lambda: NOW)
    stale = staged(staged_at=(NOW - timedelta(minutes=16)).isoformat())
    future = staged(staged_at=(NOW + timedelta(seconds=1)).isoformat())

    with pytest.raises(EvidenceRejected, match="not current"):
        registry.register_staged_candidate(candidate=candidate(), staged=stale)
    with pytest.raises(EvidenceRejected, match="not current"):
        registry.register_staged_candidate(candidate=candidate(), staged=future)


def test_evidence_expires_and_is_removed_from_registry():
    registry = make_registry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    later = make_registry(clock=lambda: NOW + timedelta(minutes=16))
    later._entries[evidence.evidence_id] = evidence

    with pytest.raises(EvidenceNotFound):
        later.get(evidence.evidence_id)


def test_binding_is_digest_specific_and_revocable():
    registry = make_registry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    first = registry.bind_to_plan(evidence_id=evidence.evidence_id, plan_digest=PLAN_DIGEST)
    second = registry.bind_to_plan(evidence_id=evidence.evidence_id, plan_digest="e" * 64)

    assert first.approval_digest != second.approval_digest
    registry.revoke(evidence.evidence_id)
    with pytest.raises(EvidenceNotFound):
        registry.get(evidence.evidence_id)


def test_default_registry_accepts_matching_manifest_publisher_without_user_pin():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    assert evidence.publisher == "DBeaver Corp"


def test_registry_rejects_signer_subject_mismatch_even_when_windows_trusts_chain():
    registry = make_registry(clock=lambda: NOW)
    with pytest.raises(EvidenceRejected, match="does not match"):
        registry.register_staged_candidate(
            candidate=candidate(),
            staged=staged(signature_subject="CN=Unrelated Publisher"),
        )



def test_registry_accepts_unrelated_package_with_exact_manifest_publisher_match():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    generic_candidate = candidate().model_copy(update={
        "package_id": "Acme.Editor",
        "package_name": "Acme Editor",
        "publisher": "Acme Inc",
        "publisher_verification": "NOT_CHECKED",
        "official_version": None,
        "official_release_url": None,
        "official_asset_sha256": None,
        "official_asset_id": None,
        "installer_url": "https://downloads.acme.example/editor.exe",
        "installer_domain": "downloads.acme.example",
    })
    generic_staged = staged(
        package_id="Acme.Editor",
        signature_subject="CN=Acme Editor, O=Acme Inc",
        official_release_url=None,
    )
    evidence = registry.register_staged_candidate(candidate=generic_candidate, staged=generic_staged)
    assert evidence.package_id == "Acme.Editor"
    assert evidence.official_release_url is None
    assert evidence.signature_sha256 == "d" * 64


def test_registry_rejects_generic_package_when_manifest_publisher_does_not_match():
    registry = SoftwareEvidenceRegistry(clock=lambda: NOW)
    generic_candidate = candidate().model_copy(update={
        "package_id": "Acme.Editor",
        "publisher": "Acme Inc",
        "publisher_verification": "NOT_CHECKED",
        "official_version": None,
        "official_release_url": None,
        "official_asset_sha256": None,
        "official_asset_id": None,
    })
    with pytest.raises(EvidenceRejected, match="does not match"):
        registry.register_staged_candidate(
            candidate=generic_candidate,
            staged=staged(
                package_id="Acme.Editor",
                signature_subject="CN=Evil Corp, O=Evil Corp",
                official_release_url=None,
            ),
        )

def test_approval_digest_changes_when_signer_certificate_fingerprint_changes():
    registry = make_registry(clock=lambda: NOW)
    evidence = registry.register_staged_candidate(candidate=candidate(), staged=staged())
    original = build_install_approval_binding(
        plan_digest=PLAN_DIGEST,
        evidence=evidence,
    )
    rotated = evidence.model_copy(update={"signature_sha256": "e" * 64})
    changed = build_install_approval_binding(
        plan_digest=PLAN_DIGEST,
        evidence=rotated,
    )

    assert original.approval_digest != changed.approval_digest
