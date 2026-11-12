"""Tests for read-only, fail-closed WinGet manifest discovery."""

import base64
import json

import pytest

from agent_backend.software_discovery import (
    DiscoveryNotFound,
    DiscoveryUnavailable,
    WinGetManifestRepository,
)

COMMIT = "a" * 40
PACKAGE_ID = "DBeaver.DBeaver.Community"
VERSION = "25.3.0"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._body = json.dumps(payload).encode()

    def iter_content(self, chunk_size):
        yield self._body


def request_path(url):
    return url.split("://", 1)[1].split("/", 1)[1].split("?", 1)[0]


class FakeSource:
    def __init__(self, *, bad_scope=False, bad_hash=False, bad_url=False):
        self.calls = []
        installer = {
            "Architecture": "x64",
            "Scope": "user" if not bad_scope else "machine",
            "InstallerType": "msi",
            "InstallerUrl": "https://dbeaver.io/files/dbeaver.msi",
            "InstallerSha256": "b" * 64,
        }
        if bad_hash:
            installer["InstallerSha256"] = "not-a-hash"
        if bad_url:
            installer["InstallerUrl"] = "http://127.0.0.1/installer.exe"
        self.documents = {
            "DBeaver.DBeaver.Community.yaml": {
                "PackageIdentifier": PACKAGE_ID,
                "PackageVersion": VERSION,
                "DefaultLocale": "en-US",
                "ManifestType": "version",
                "ManifestVersion": "1.10.0",
            },
            "DBeaver.DBeaver.Community.locale.en-US.yaml": {
                "PackageIdentifier": PACKAGE_ID,
                "PackageVersion": VERSION,
                "PackageLocale": "en-US",
                "PackageName": "DBeaver Community",
                "Publisher": "DBeaver Corp",
                "ManifestType": "defaultLocale",
                "ManifestVersion": "1.10.0",
            },
            "DBeaver.DBeaver.Community.installer.yaml": {
                "PackageIdentifier": PACKAGE_ID,
                "PackageVersion": VERSION,
                "ManifestType": "installer",
                "ManifestVersion": "1.10.0",
                "InstallerType": "msi",
                "Installers": [installer],
            },
        }

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        path = request_path(url)
        if path.endswith("/commits/master"):
            payload = {"sha": COMMIT}
        elif path.endswith("/DBeaver/DBeaver/Community"):
            payload = [{"name": VERSION, "type": "dir"}]
        elif path.endswith(f"/{VERSION}"):
            payload = [
                {"name": name, "type": "file"}
                for name in self.documents
            ]
        else:
            filename = path.rsplit("/", 1)[-1]
            document = self.documents[filename]
            raw = json.dumps(document).encode()
            payload = {
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
            }
        return FakeResponse(payload)


def test_discovery_reads_source_and_returns_conditional_candidate_only():
    source = FakeSource()
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "CONDITIONAL"
    assert result.candidate is not None
    assert result.candidate.publisher == "DBeaver Corp"
    assert result.candidate.installer_domain == "dbeaver.io"
    assert result.candidate.installer_sha256 == "b" * 64
    assert "installer_authenticode_signature_not_yet_verified" in result.candidate.limitations
    assert all(call[1]["allow_redirects"] is False for call in source.calls)
    assert all("winget.exe" not in call[0] for call in source.calls)
    assert any(
        "/contents/manifests/d/DBeaver/DBeaver/Community" in call[0]
        for call in source.calls
    )


def test_discovery_requires_explicit_version_and_never_guesses_latest():
    source = FakeSource()
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=None,
        architecture="x64",
    )

    assert result.status == "VERSION_REQUIRED"
    assert result.candidate is None
    assert result.available_versions == (VERSION,)


@pytest.mark.parametrize(
    "source",
    [
        FakeSource(bad_scope=True),
        FakeSource(bad_hash=True),
        FakeSource(bad_url=True),
    ],
)
def test_discovery_fails_closed_on_unsafe_or_incomplete_installer(source):
    with pytest.raises(DiscoveryUnavailable):
        WinGetManifestRepository(http_get=source.get).discover(
            package_id=PACKAGE_ID,
            version=VERSION,
            architecture="x64",
        )


def test_manifest_schema_version_with_long_digit_run_is_rejected():
    source = FakeSource()
    original_get = source.get

    def malformed_version_get(url, **kwargs):
        response = original_get(url, **kwargs)
        if url.endswith(".yaml"):
            payload = json.loads(response._body)
            document = json.loads(base64.b64decode(payload["content"]))
            document["ManifestVersion"] = ("9" * 100_000) + ".0.0"
            payload["content"] = base64.b64encode(json.dumps(document).encode()).decode()
            response._body = json.dumps(payload).encode()
        return response

    with pytest.raises(DiscoveryUnavailable):
        WinGetManifestRepository(http_get=malformed_version_get).discover(
            package_id=PACKAGE_ID,
            version=VERSION,
            architecture="x64",
        )


def test_missing_package_is_not_found():
    class MissingSource(FakeSource):
        def get(self, url, **kwargs):
            if request_path(url).endswith("/DBeaver/DBeaver/Community"):
                return FakeResponse({"message": "Not Found"}, status_code=404)
            return super().get(url, **kwargs)

    with pytest.raises(DiscoveryNotFound):
        WinGetManifestRepository(http_get=MissingSource().get).discover(
            package_id=PACKAGE_ID,
            version=VERSION,
            architecture="x64",
        )


@pytest.mark.parametrize("package_id", ["", "../evil.pkg", "NoDot", "A..B", "A.B.C.D.E", "a" * 161])
def test_invalid_package_identifiers_are_rejected_before_network(package_id):
    source = FakeSource()
    with pytest.raises(ValueError):
        WinGetManifestRepository(http_get=source.get).discover(
            package_id=package_id,
            version=VERSION,
            architecture="x64",
        )
    assert source.calls == []


def test_repository_requests_are_pinned_to_one_commit_and_fixed_origin():
    source = FakeSource()
    WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert all(
        call[0].startswith("https://api.github.com/repos/microsoft/winget-pkgs/")
        for call in source.calls
    )
    manifest_calls = [call for call in source.calls if "commits/master" not in call[0]]
    assert all(call[1]["params"]["ref"] == COMMIT for call in manifest_calls)
