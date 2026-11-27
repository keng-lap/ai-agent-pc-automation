"""Tests for bounded installer staging and fail-closed verification."""

import hashlib
from pathlib import Path

import pytest

from agent_backend.software_discovery import InstallerCandidate
from agent_backend.software_staging import InstallerStageError, InstallerStager


class FakeResponse:
    def __init__(self, body=b"verified-installer-bytes", *, status_code=200, headers=None, chunk_size=5):
        self.status_code = status_code
        self.headers = headers or {"Content-Length": str(len(body))}
        self.body = body
        self.chunk_size = chunk_size
        self.closed = False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), self.chunk_size):
            yield self.body[offset : offset + self.chunk_size]

    def close(self):
        self.closed = True


class AcceptSignature:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.paths = []

    def verify(self, path):
        self.paths.append(path)
        return self.accepted


def make_candidate(body=b"verified-installer-bytes"):
    digest = hashlib.sha256(body).hexdigest()
    return InstallerCandidate(
        package_id="Acme.Editor",
        package_name="Acme Editor",
        publisher="Acme Inc",
        version="26.2.4",
        architecture="x64",
        scope="user",
        installer_type="exe",
        installer_url="https://github.com/acme/editor/releases/download/26.2.4/acme-editor-26.2.4-windows-x86_64.exe",
        installer_domain="github.com",
        installer_sha256=digest,
        manifest_sha256="a" * 64,
        repository_commit="b" * 40,
        manifest_source_url="https://github.com/microsoft/winget-pkgs/tree/main",
        checked_at="2026-11-12T00:00:00Z",
        publisher_verification="VERIFIED",
        official_version="26.2.4",
        official_release_url="https://github.com/acme/editor/releases/tag/26.2.4",
        official_asset_sha256=digest,
        official_asset_id=12345,
        limitations=("installer_authenticode_signature_not_yet_verified",),
    )


def test_stage_downloads_hashes_and_verifies_without_executing(tmp_path):
    body = b"verified-installer-bytes"
    response = FakeResponse(body)
    signature = AcceptSignature()
    calls = []

    def http_get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    staged = InstallerStager(
        http_get=http_get,
        signature_verifier=signature,
        clock=lambda: "2026-11-12T00:00:00Z",
    ).stage(make_candidate(body), staging_root=tmp_path)

    path = Path(staged.file_path)
    assert path.parent == tmp_path
    assert path.read_bytes() == body
    assert staged.sha256 == hashlib.sha256(body).hexdigest()
    assert staged.file_size == len(body)
    assert staged.authenticode_valid is True
    assert response.closed is True
    assert signature.paths == [path] or signature.paths[0].suffix == ".exe"
    assert calls[0][0] == make_candidate(body).installer_url
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["stream"] is True
    assert list(tmp_path.glob("*.part.exe")) == []



def test_generic_package_uses_manifest_url_and_hash_without_vendor_release_api(tmp_path):
    body = b"generic-signed-installer"
    digest = hashlib.sha256(body).hexdigest()
    candidate = make_candidate(body).model_copy(update={
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
        "installer_sha256": digest,
    })
    calls = []
    staged = InstallerStager(
        http_get=lambda url, **kwargs: (calls.append(url) or FakeResponse(body)),
        signature_verifier=AcceptSignature(),
        clock=lambda: "2026-11-12T00:00:00Z",
    ).stage(candidate, staging_root=tmp_path)
    assert calls == ["https://downloads.acme.example/editor.exe"]
    assert staged.package_id == "Acme.Editor"
    assert staged.sha256 == digest
    assert staged.official_release_url is None


def test_generic_package_rejects_unexpected_unverified_vendor_claims(tmp_path):
    candidate = make_candidate().model_copy(update={
        "package_id": "Acme.Editor",
        "publisher_verification": "NOT_CHECKED",
        "official_version": "1.0.0",
        "official_release_url": "https://vendor.example/releases/1.0.0",
        "official_asset_sha256": None,
        "official_asset_id": None,
    })
    with pytest.raises(InstallerStageError, match="unexpected vendor release"):
        InstallerStager(signature_verifier=AcceptSignature()).stage(candidate, staging_root=tmp_path)

def test_unverified_candidate_is_rejected_before_network_or_file_creation(tmp_path):
    candidate = make_candidate().model_copy(update={"publisher_verification": "MISMATCH"})
    calls = []

    with pytest.raises(InstallerStageError, match="not matched"):
        InstallerStager(http_get=lambda *args, **kwargs: calls.append(args)).stage(
            candidate,
            staging_root=tmp_path,
        )

    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_hash_mismatch_removes_partial_file(tmp_path):
    body = b"wrong-installer"
    response = FakeResponse(body)
    signature = AcceptSignature()

    with pytest.raises(InstallerStageError, match="SHA-256"):
        InstallerStager(
            http_get=lambda *args, **kwargs: response,
            signature_verifier=signature,
        ).stage(make_candidate(), staging_root=tmp_path)

    assert response.closed is True
    assert signature.paths == []
    assert list(tmp_path.iterdir()) == []


def test_invalid_authenticode_signature_removes_downloaded_file(tmp_path):
    body = b"verified-installer-bytes"
    response = FakeResponse(body)
    signature = AcceptSignature(accepted=False)

    with pytest.raises(InstallerStageError, match="Authenticode"):
        InstallerStager(
            http_get=lambda *args, **kwargs: response,
            signature_verifier=signature,
        ).stage(make_candidate(body), staging_root=tmp_path)

    assert response.closed is True
    assert len(signature.paths) == 1
    assert list(tmp_path.iterdir()) == []


def test_redirect_is_not_followed_and_partial_file_is_removed(tmp_path):
    response = FakeResponse(status_code=302, headers={"Location": "https://attacker.example/file.exe"})

    with pytest.raises(InstallerStageError, match="redirect target was not trusted"):
        InstallerStager(
            http_get=lambda *args, **kwargs: response,
            signature_verifier=AcceptSignature(),
        ).stage(make_candidate(), staging_root=tmp_path)

    assert response.closed is True
    assert list(tmp_path.iterdir()) == []



def test_generic_installer_redirect_cannot_escape_manifest_host(tmp_path):
    candidate = make_candidate().model_copy(update={
        "package_id": "Acme.Editor",
        "publisher": "Acme Inc",
        "publisher_verification": "NOT_CHECKED",
        "official_version": None,
        "official_release_url": None,
        "official_asset_sha256": None,
        "official_asset_id": None,
        "installer_url": "https://downloads.acme.example/editor.exe",
        "installer_domain": "downloads.acme.example",
    })
    response = FakeResponse(
        status_code=302,
        headers={"Location": "https://cdn.attacker.example/editor.exe"},
    )
    with pytest.raises(InstallerStageError, match="redirect target was not trusted"):
        InstallerStager(
            http_get=lambda *args, **kwargs: response,
            signature_verifier=AcceptSignature(),
        ).stage(candidate, staging_root=tmp_path)
    assert response.closed is True
    assert list(tmp_path.iterdir()) == []


def test_manifest_url_redirect_to_approved_github_asset_cdn_is_followed_without_auth(tmp_path):
    body = b"verified-installer-bytes"
    redirect = FakeResponse(
        status_code=302,
        headers={"Location": "https://release-assets.githubusercontent.com/github-production-release-asset/asset?token=temporary"},
    )
    final = FakeResponse(body)
    responses = iter([redirect, final])
    calls = []

    def http_get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    staged = InstallerStager(
        http_get=http_get,
        signature_verifier=AcceptSignature(),
    ).stage(make_candidate(body), staging_root=tmp_path)

    assert Path(staged.file_path).read_bytes() == body
    assert redirect.closed is True
    assert final.closed is True
    assert calls[0][0] == make_candidate(body).installer_url
    assert calls[1][0].startswith("https://release-assets.githubusercontent.com/")
    assert all("Authorization" not in call[1]["headers"] for call in calls)
    assert all(call[1]["allow_redirects"] is False for call in calls)


def test_oversized_content_length_is_rejected(tmp_path, monkeypatch):
    from agent_backend import software_staging

    monkeypatch.setattr(software_staging, "MAX_INSTALLER_BYTES", 8)
    response = FakeResponse(headers={"Content-Length": "9"})

    with pytest.raises(InstallerStageError, match="size limit"):
        InstallerStager(
            http_get=lambda *args, **kwargs: response,
            signature_verifier=AcceptSignature(),
        ).stage(make_candidate(), staging_root=tmp_path)

    assert response.closed is True
    assert list(tmp_path.iterdir()) == []


def test_staging_directory_must_be_absolute_and_not_a_symlink(tmp_path):
    candidate = make_candidate()
    with pytest.raises(InstallerStageError, match="absolute"):
        InstallerStager(signature_verifier=AcceptSignature()).stage(
            candidate,
            staging_root=Path("relative"),
        )



class AcceptSignatureWithSubject:
    def verify_with_subject(self, path):
        assert Path(path).is_file()
        return True, "CN=Trusted Test Publisher, O=Trusted Test Publisher"


def test_stager_carries_subject_only_from_signature_verifier(tmp_path):
    body = b"verified-installer-bytes"
    staged = InstallerStager(
        http_get=lambda *args, **kwargs: FakeResponse(body),
        signature_verifier=AcceptSignatureWithSubject(),
        clock=lambda: "2026-11-12T00:00:00Z",
    ).stage(make_candidate(body), staging_root=tmp_path)

    assert staged.authenticode_valid is True
    assert staged.signature_subject == "CN=Trusted Test Publisher, O=Trusted Test Publisher"


class AcceptSignatureWithIdentity:
    def verify_with_identity(self, path):
        assert Path(path).is_file()
        return True, "CN=Trusted Test Publisher, O=Trusted Test Publisher", "d" * 64


def test_stager_carries_verified_certificate_fingerprint(tmp_path):
    body = b"verified-installer-bytes"
    staged = InstallerStager(
        http_get=lambda *args, **kwargs: FakeResponse(body),
        signature_verifier=AcceptSignatureWithIdentity(),
        clock=lambda: "2026-11-12T00:00:00Z",
    ).stage(make_candidate(body), staging_root=tmp_path)

    assert staged.authenticode_valid is True
    assert staged.signature_subject == "CN=Trusted Test Publisher, O=Trusted Test Publisher"
    assert staged.signature_sha256 == "d" * 64


def test_installer_stage_error_exposes_safe_diagnostic_classification():
    error = InstallerStageError("installer SHA-256 did not match the approved release digest")

    assert error.failure_code == "installer_manifest_hash_mismatch"
    assert error.failure_reason == "Downloaded SHA-256 did not match the WinGet manifest digest."
