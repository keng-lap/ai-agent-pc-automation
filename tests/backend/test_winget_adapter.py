from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agent_backend.software_approval import (
    VerifiedPackageEvidence,
    build_install_approval_binding,
)
from agent_backend.winget_adapter import (
    WinGetAdapterError,
    build_install_arguments,
    build_local_manifest_documents,
    cleanup_prepared_install,
    prepare_approved_install,
)


def _binding(**overrides):
    now = datetime.now(UTC)
    values = {
        "evidence_id": "evidence-0123456789abcdef",
        "package_id": "Contoso.Sample",
        "package_name": "Contoso Sample",
        "publisher": "Contoso Ltd.",
        "version": "2.4.1",
        "source": "winget",
        "installer_type": "msi",
        "installer_url": "https://downloads.contoso.example/sample-2.4.1.msi",
        "official_release_url": "https://contoso.example/releases/2.4.1",
        "manifest_source_url": "https://github.com/microsoft/winget-pkgs/tree/" + "a" * 40,
        "repository_commit": "a" * 40,
        "installer_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "architecture": "x64",
        "scope": "user",
        "signature_subject": "CN=Contoso Ltd.",
        "signature_sha256": "d" * 64,
        "verified_at": now - timedelta(seconds=1),
        "expires_at": now + timedelta(minutes=10),
    }
    values.update(overrides)
    evidence = VerifiedPackageEvidence.model_validate(values)
    return build_install_approval_binding(plan_digest="e" * 64, evidence=evidence), now


def test_local_manifest_pins_exact_approved_installer_and_hash():
    binding, _ = _binding()
    documents = build_local_manifest_documents(binding)

    assert set(documents) == {
        "Contoso.Sample.yaml",
        "Contoso.Sample.locale.en-US.yaml",
        "Contoso.Sample.installer.yaml",
    }
    installer = yaml.safe_load(documents["Contoso.Sample.installer.yaml"])
    assert installer["PackageIdentifier"] == "Contoso.Sample"
    assert installer["PackageVersion"] == "2.4.1"
    assert installer["InstallerType"] == "msi"
    assert installer["Installers"] == [
        {
            "Architecture": "x64",
            "Scope": "user",
            "InstallerUrl": "https://downloads.contoso.example/sample-2.4.1.msi",
            "InstallerSha256": "b" * 64,
        }
    ]


def test_manifest_does_not_copy_untrusted_installer_switches_or_commands():
    binding, _ = _binding()
    documents = build_local_manifest_documents(binding)
    combined = "\n".join(documents.values()).casefold()

    assert "installer switches" not in combined
    assert "powershell" not in combined
    assert "--override" not in combined
    assert "cmd.exe" not in combined


def test_install_arguments_use_only_local_manifest_and_user_scope(tmp_path):
    binding, _ = _binding()
    prepared = prepare_approved_install(binding, work_root=tmp_path)
    manifest_dir = Path(prepared.manifest_directory)

    args = build_install_arguments(binding, prepared, work_root=tmp_path)

    assert args == (
        "install",
        "--manifest",
        str(manifest_dir),
        "--scope",
        "user",
        "--architecture",
        "x64",
        "--silent",
        "--disable-interactivity",
        "--skip-dependencies",
        "--no-upgrade",
    )
    assert "--id" not in args
    assert "--source" not in args
    assert "--override" not in args
    assert "--ignore-security-hash" not in args
    assert "--accept-package-agreements" not in args


@pytest.mark.parametrize(
    "overrides",
    [
        {"installer_type": "portable"},
        {"scope": "machine"},
        {"source": "chocolatey"},
        {"installer_url": "http://downloads.contoso.example/sample-2.4.1.msi"},
        {"installer_url": "https://downloads.contoso.example/sample-2.4.1.exe"},
    ],
)
def test_unsupported_or_mismatched_evidence_is_rejected(overrides):
    with pytest.raises((WinGetAdapterError, ValidationError)):
        binding, _ = _binding(**overrides)
        build_local_manifest_documents(binding)


def test_prepare_requires_fresh_approval_and_writes_only_three_files(tmp_path):
    binding, now = _binding()
    prepared = prepare_approved_install(binding, work_root=tmp_path, now=now)

    directory = Path(prepared.manifest_directory)
    assert directory.parent == tmp_path
    assert len(list(directory.iterdir())) == 3
    assert prepared.package_id == "Contoso.Sample"
    assert prepared.version == "2.4.1"
    assert prepared.installer_sha256 == "b" * 64
    assert prepared.approval_digest == binding.approval_digest

    cleanup_prepared_install(prepared, work_root=tmp_path)
    assert not directory.exists()


def test_prepare_rejects_expired_approval(tmp_path):
    binding, now = _binding()
    with pytest.raises(WinGetAdapterError, match="expired"):
        prepare_approved_install(
            binding,
            work_root=tmp_path,
            now=binding.evidence.expires_at,
        )
    assert list(tmp_path.iterdir()) == []


def test_prepare_rejects_symlink_work_root(tmp_path):
    binding, now = _binding()
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(WinGetAdapterError, match="non-symlink"):
        prepare_approved_install(binding, work_root=link, now=now)


def test_install_arguments_reject_tampered_manifest(tmp_path):
    binding, _ = _binding()
    prepared = prepare_approved_install(binding, work_root=tmp_path)
    manifest_dir = Path(prepared.manifest_directory)
    (manifest_dir / "Contoso.Sample.installer.yaml").write_text("InstallerUrl: https://attacker.example/x.msi", encoding="utf-8")

    with pytest.raises(WinGetAdapterError, match="content"):
        build_install_arguments(binding, prepared, work_root=tmp_path)


def test_install_arguments_reject_extra_manifest_files(tmp_path):
    binding, _ = _binding()
    prepared = prepare_approved_install(binding, work_root=tmp_path)
    manifest_dir = Path(prepared.manifest_directory)
    (manifest_dir / "unexpected.yaml").write_text("ManifestType: installer", encoding="utf-8")

    with pytest.raises(WinGetAdapterError, match="file set"):
        build_install_arguments(binding, prepared, work_root=tmp_path)
