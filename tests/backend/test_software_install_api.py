"""Tests for Windows-local verified install proposal creation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent_backend import software_install_api as api
from agent_backend.software_approval import VerifiedPackageEvidence
from agent_backend.software_discovery import InstallerCandidate
from agent_backend.software_evidence import EvidenceRejected
from agent_backend.software_staging import StagedInstaller

NOW = datetime.now(UTC)


def make_candidate(**changes):
    values = {
        "package_id": "DBeaver.DBeaver.Community",
        "package_name": "DBeaver Community Edition",
        "publisher": "DBeaver Corp",
        "version": "26.2.5",
        "architecture": "x64",
        "scope": "user",
        "installer_type": "exe",
        "installer_silent_switch": "/S",
        "installer_url": "https://github.com/dbeaver/dbeaver/releases/download/26.2.5/dbeaver-ce-26.2.5-windows-x86_64.exe",
        "installer_domain": "github.com",
        "installer_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "repository_commit": "c" * 40,
        "manifest_source_url": "https://github.com/microsoft/winget-pkgs/tree/c",
        "checked_at": NOW.isoformat(),
        "publisher_verification": "VERIFIED",
        "official_version": "26.2.5",
        "official_release_url": "https://github.com/dbeaver/dbeaver/releases/tag/26.2.5",
        "official_asset_sha256": "a" * 64,
        "official_asset_id": 12345,
        "limitations": (),
    }
    values.update(changes)
    return InstallerCandidate(**values)


def make_evidence():
    return VerifiedPackageEvidence(
        evidence_id="e" * 32,
        package_id="DBeaver.DBeaver.Community",
        package_name="DBeaver Community Edition",
        publisher="DBeaver Corp",
        version="26.2.5",
        source="winget",
        installer_type="exe",
        installer_silent_switch="/S",
        installer_url="https://github.com/dbeaver/dbeaver/releases/download/26.2.5/dbeaver-ce-26.2.5-windows-x86_64.exe",
        official_release_url="https://github.com/dbeaver/dbeaver/releases/tag/26.2.5",
        manifest_source_url="https://github.com/microsoft/winget-pkgs/tree/c",
        repository_commit="c" * 40,
        installer_sha256="a" * 64,
        manifest_sha256="b" * 64,
        architecture="x64",
        scope="user",
        signature_subject="CN=DBeaver Corporation",
        signature_sha256="d" * 64,
        verified_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def make_request(tmp_path):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(job_store_path=tmp_path / "jobs.sqlite")),
        state=SimpleNamespace(principal=SimpleNamespace(owner_sub="owner-1")),
    )


def test_verified_candidate_creates_an_exact_install_plan_and_cleans_staged_file(monkeypatch, tmp_path):
    candidate = make_candidate()
    staged_path = tmp_path / "installer.exe"
    staged_path.write_bytes(b"verified installer")
    staged = StagedInstaller(
        package_id=candidate.package_id,
        version=candidate.version,
        architecture=candidate.architecture,
        file_path=str(staged_path),
        file_size=18,
        sha256="a" * 64,
        authenticode_valid=True,
        signature_subject="CN=DBeaver Corporation",
        signature_sha256="d" * 64,
        official_release_url=candidate.official_release_url,
        staged_at=NOW.isoformat(),
    )
    evidence = make_evidence()
    monkeypatch.setattr(api.sys, "platform", "win32")
    monkeypatch.setattr(api._repository, "discover", lambda **_kwargs: SimpleNamespace(status="CONDITIONAL", candidate=candidate))
    monkeypatch.setattr(api._stager, "stage", lambda *_args, **_kwargs: staged)
    monkeypatch.setattr(api.software_evidence_registry, "register_staged_candidate", lambda **_kwargs: evidence)

    response = api.create_software_install_proposal(
        api.SoftwareInstallProposalRequest(
            package_id=candidate.package_id,
            version=candidate.version,
            architecture="x64",
        ),
        request=make_request(tmp_path),
    )

    plan = api.software_install_plan_store.get(response.plan_id, owner_id="owner-1")
    assert response.evidence_id == evidence.evidence_id
    assert response.package_id == evidence.package_id
    assert response.version == evidence.version
    assert response.notice == "VERIFIED_PROPOSAL_REQUIRES_EXACT_ACTION_TOTP"
    assert plan.evidence_id == evidence.evidence_id
    assert plan.plan_digest
    from agent_backend.software_install_plans import InstallPlanNotFound

    with pytest.raises(InstallPlanNotFound):
        api.software_install_plan_store.get(response.plan_id, owner_id="different-owner")
    assert not staged_path.exists()



def test_generic_package_proposal_uses_publisher_independent_sha256_trust_path(monkeypatch, tmp_path):
    candidate = make_candidate(
        package_id="Acme.Editor",
        package_name="Acme Editor",
        publisher="Acme Inc",
        installer_url="https://downloads.acme.example/editor.exe",
        installer_domain="downloads.acme.example",
        publisher_verification="NOT_CHECKED",
        official_version=None,
        official_release_url=None,
        official_asset_sha256=None,
        official_asset_id=None,
    )
    staged_path = tmp_path / "generic-installer.exe"
    staged_path.write_bytes(b"verified installer")
    staged = StagedInstaller(
        package_id=candidate.package_id,
        version=candidate.version,
        architecture=candidate.architecture,
        file_path=str(staged_path),
        file_size=18,
        sha256="a" * 64,
        authenticode_valid=True,
        signature_subject="CN=Acme Editor, O=Acme Inc",
        signature_sha256="d" * 64,
        official_release_url=None,
        staged_at=NOW.isoformat(),
    )
    evidence = make_evidence().model_copy(update={
        "package_id": "Acme.Editor",
        "package_name": "Acme Editor",
        "publisher": "Acme Inc",
        "installer_url": "https://downloads.acme.example/editor.exe",
        "official_release_url": None,
    })
    stage_calls = []
    monkeypatch.setattr(api.sys, "platform", "win32")
    monkeypatch.setattr(api._repository, "discover", lambda **_kwargs: SimpleNamespace(status="CONDITIONAL", candidate=candidate))
    monkeypatch.setattr(api._stager, "stage", lambda *args, **kwargs: (stage_calls.append(args) or staged))
    monkeypatch.setattr(api.software_evidence_registry, "register_staged_candidate", lambda **_kwargs: evidence)
    response = api.create_software_install_proposal(
        api.SoftwareInstallProposalRequest(package_id="Acme.Editor", version=candidate.version),
        request=make_request(tmp_path),
    )
    assert response.package_id == "Acme.Editor"
    assert stage_calls
    assert not staged_path.exists()


def test_unsupported_installer_type_is_rejected_before_staging(monkeypatch, tmp_path):
    candidate = make_candidate(installer_type="inno")
    stage_calls = []
    monkeypatch.setattr(api.sys, "platform", "win32")
    discovery_calls = []

    def discover(**kwargs):
        discovery_calls.append(kwargs)
        assert kwargs == {
            "package_id": candidate.package_id,
            "version": candidate.version,
            "architecture": "x64",
            "scope": "user",
        }
        return SimpleNamespace(status="CONDITIONAL", candidate=candidate)

    monkeypatch.setattr(api._repository, "discover", discover)
    monkeypatch.setattr(api._stager, "stage", lambda *args, **kwargs: stage_calls.append(args))

    with pytest.raises(Exception) as error:
        api.create_software_install_proposal(
            api.SoftwareInstallProposalRequest(
                package_id=candidate.package_id,
                version=candidate.version,
            ),
            request=make_request(tmp_path),
        )

    assert getattr(error.value, "status_code", None) == 409
    assert discovery_calls == [{
        "package_id": candidate.package_id,
        "version": candidate.version,
        "architecture": "x64",
        "scope": "user",
    }]
    assert stage_calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"official_version": "26.2.4"},
        {"official_asset_sha256": "f" * 64},
    ],
)
def test_official_release_version_and_digest_must_match_before_download(monkeypatch, tmp_path, changes):
    candidate = make_candidate(**changes)
    stage_calls = []
    monkeypatch.setattr(api.sys, "platform", "win32")
    monkeypatch.setattr(api._repository, "discover", lambda **_kwargs: SimpleNamespace(status="CONDITIONAL", candidate=candidate))
    monkeypatch.setattr(api._stager, "stage", lambda *args, **kwargs: stage_calls.append(args))

    with pytest.raises(Exception) as error:
        api.create_software_install_proposal(
            api.SoftwareInstallProposalRequest(
                package_id=candidate.package_id,
                version=candidate.version,
            ),
            request=make_request(tmp_path),
        )

    assert getattr(error.value, "status_code", None) == 409
    assert stage_calls == []


def test_unverified_official_release_is_rejected_before_download(monkeypatch, tmp_path):
    candidate = make_candidate(publisher_verification="NOT_CHECKED")
    stage_calls = []
    monkeypatch.setattr(api.sys, "platform", "win32")
    monkeypatch.setattr(api._repository, "discover", lambda **_kwargs: SimpleNamespace(status="CONDITIONAL", candidate=candidate))
    monkeypatch.setattr(api._stager, "stage", lambda *args, **kwargs: stage_calls.append(args))

    with pytest.raises(Exception) as error:
        api.create_software_install_proposal(
            api.SoftwareInstallProposalRequest(
                package_id=candidate.package_id,
                version=candidate.version,
            ),
            request=make_request(tmp_path),
        )

    assert getattr(error.value, "status_code", None) == 409
    assert stage_calls == []


def test_proposal_endpoint_is_windows_only(monkeypatch, tmp_path):
    monkeypatch.setattr(api.sys, "platform", "linux")

    with pytest.raises(Exception) as error:
        api.create_software_install_proposal(
            api.SoftwareInstallProposalRequest(
                package_id="DBeaver.DBeaver.Community",
                version="26.2.5",
            ),
            request=make_request(tmp_path),
        )

    assert getattr(error.value, "status_code", None) == 503



def test_readiness_exposes_sha256_and_authenticode_integrity_policy(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_AGENT_DBEAVER_SIGNER_SHA256", raising=False)
    request = make_request(tmp_path)
    request.app.state.real_install_enabled = False
    request.app.state.real_install_release_authorization = None
    ready = api.get_software_install_readiness(request)
    assert ready["notice"] == "NO_INSTALL_IS_STARTED_BY_THIS_ENDPOINT"
    assert ready["package_allowlist_enabled"] is False
    assert ready["installer_trust_mode"] == "WINGET_MANIFEST_SHA256_AND_AUTHENTICODE_SIGNATURE_INTEGRITY"
    assert "publisher" not in str(ready).casefold()
    assert ready["supported_package_ids"] == []
    assert "AI_AGENT_DBEAVER_SIGNER_SHA256" not in str(ready)
    assert "d" * 64 not in str(ready)


def test_readiness_uses_worker_configuration_not_process_environment(monkeypatch, tmp_path):
    from agent_backend.config import RealInstallReleaseAuthorization

    monkeypatch.setattr(api.sys, "platform", "win32")
    monkeypatch.setenv("AI_AGENT_ENABLE_REAL_INSTALL", "1")
    request = make_request(tmp_path)
    request.app.state.real_install_enabled = False
    request.app.state.real_install_release_authorization = None
    assert api.get_software_install_readiness(request)["real_install_enabled"] is False

    authorization = RealInstallReleaseAuthorization(
        task_id="P6-609-C",
        package_id="Contoso.Editor",
        version="2.4.1",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        nonce="a" * 64,
    )
    request.app.state.real_install_enabled = True
    request.app.state.real_install_release_authorization = authorization
    ready = api.get_software_install_readiness(request)
    assert ready["real_install_enabled"] is True
    assert ready["real_install_release_package_id"] == "Contoso.Editor"
    assert ready["real_install_release_version"] == "2.4.1"

    expired = RealInstallReleaseAuthorization(
        task_id="P6-609-C",
        package_id="Contoso.Editor",
        version="2.4.1",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        nonce="b" * 64,
    )
    request.app.state.real_install_release_authorization = expired
    assert api.get_software_install_readiness(request)["real_install_enabled"] is False


def test_exe_without_manifest_silent_switch_is_rejected_before_staging(monkeypatch, tmp_path):
    candidate = make_candidate(installer_silent_switch=None)
    stage_calls = []
    monkeypatch.setattr(api.sys, "platform", "win32")
    discovery_calls = []

    def discover(**kwargs):
        discovery_calls.append(kwargs)
        assert kwargs == {
            "package_id": candidate.package_id,
            "version": candidate.version,
            "architecture": "x64",
            "scope": "user",
        }
        return SimpleNamespace(status="CONDITIONAL", candidate=candidate)

    monkeypatch.setattr(api._repository, "discover", discover)
    monkeypatch.setattr(api._stager, "stage", lambda *args, **kwargs: stage_calls.append(args))

    with pytest.raises(Exception) as error:
        api.create_software_install_proposal(
            api.SoftwareInstallProposalRequest(package_id=candidate.package_id, version=candidate.version),
            request=make_request(tmp_path),
        )

    assert getattr(error.value, "status_code", None) == 409
    assert stage_calls == []

def test_proposal_request_rejects_machine_scope_until_elevated_helper_is_available():
    with pytest.raises(ValidationError):
        api.SoftwareInstallProposalRequest(
            package_id="DBeaver.DBeaver.Community",
            version="26.2.5",
            architecture="x64",
            scope="machine",
        )

