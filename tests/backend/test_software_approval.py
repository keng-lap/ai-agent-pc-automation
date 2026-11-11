from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from agent_backend.software_approval import (
    VerifiedPackageEvidence,
    build_install_approval_binding,
    digest_install_approval,
)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PLAN_DIGEST = "a" * 64


def evidence(**overrides):
    values = {
        "evidence_id": "winget:manifest:abc123",
        "package_id": "DBeaver.DBeaver.Community",
        "publisher": "DBeaver Corporation",
        "version": "25.2.0",
        "source": "winget",
        "installer_url": "https://download.example.test/dbeaver.exe",
        "installer_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "architecture": "x64",
        "scope": "user",
        "signature_subject": "DBeaver Corporation",
        "verified_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    values.update(overrides)
    return VerifiedPackageEvidence(**values)


def test_binding_digest_covers_all_material_package_facts():
    original = evidence()
    changed = evidence(version="25.2.1")

    assert digest_install_approval(plan_digest=PLAN_DIGEST, evidence=original) != (
        digest_install_approval(plan_digest=PLAN_DIGEST, evidence=changed)
    )


def test_binding_digest_covers_plan_and_installer_hash():
    original = evidence()
    assert digest_install_approval(
        plan_digest=PLAN_DIGEST,
        evidence=original,
    ) != digest_install_approval(
        plan_digest="d" * 64,
        evidence=original,
    )
    assert digest_install_approval(
        plan_digest=PLAN_DIGEST,
        evidence=original,
    ) != digest_install_approval(
        plan_digest=PLAN_DIGEST,
        evidence=evidence(installer_sha256="e" * 64),
    )


def test_binding_is_immutable_and_digest_checked():
    verified = evidence()
    binding = build_install_approval_binding(
        plan_digest=PLAN_DIGEST,
        evidence=verified,
    )

    with pytest.raises(ValidationError):
        binding.approval_digest = "f" * 64

    with pytest.raises(ValidationError):
        type(binding)(
            plan_digest=PLAN_DIGEST,
            evidence=verified,
            approval_digest="f" * 64,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"installer_url": "http://download.example.test/app.exe"},
        {"installer_url": "https://user:pass@download.example.test/app.exe"},
        {"installer_url": "https://download.example.test/app.exe#fragment"},
        {"installer_sha256": "not-a-digest"},
        {"manifest_sha256": "not-a-digest"},
        {"scope": "machine"},
        {"architecture": "unknown"},
        {"expires_at": NOW + timedelta(minutes=16)},
        {"expires_at": NOW},
    ],
)
def test_invalid_or_overbroad_package_evidence_is_rejected(overrides):
    with pytest.raises(ValidationError):
        evidence(**overrides)


def test_evidence_expiry_is_enforced_at_approval_time():
    binding = build_install_approval_binding(
        plan_digest=PLAN_DIGEST,
        evidence=evidence(),
    )
    binding.ensure_fresh(now=NOW + timedelta(minutes=9))

    with pytest.raises(ValueError, match="not current"):
        binding.ensure_fresh(now=NOW + timedelta(minutes=10))


def test_digest_rejects_malformed_plan_digest():
    with pytest.raises(ValueError):
        digest_install_approval(plan_digest="not-a-digest", evidence=evidence())
