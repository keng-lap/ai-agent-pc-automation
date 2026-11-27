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
PACKAGE_ID = "Acme.Editor"
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
    def __init__(
        self, *, bad_scope=False, bad_hash=False, bad_url=False, wrap_base64=False, publisher_url=None,
    ):
        self.calls = []
        self.wrap_base64 = wrap_base64
        installer = {
            "Architecture": "x64",
            "Scope": "user" if not bad_scope else "machine",
            "InstallerType": "exe",
            "InstallerSwitches": {"Silent": "/S"},
            "InstallerUrl": f"https://github.com/acme/editor/releases/download/{VERSION}/acme-editor-{VERSION}-windows-x86_64.exe",
            "InstallerSha256": "b" * 64,
        }
        if bad_hash:
            installer["InstallerSha256"] = "not-a-hash"
        if bad_url:
            installer["InstallerUrl"] = "http://127.0.0.1/installer.exe"
        self.documents = {
            "Acme.Editor.yaml": {
                "PackageIdentifier": PACKAGE_ID,
                "PackageVersion": VERSION,
                "DefaultLocale": "en-US",
                "ManifestType": "version",
                "ManifestVersion": "1.10.0",
            },
            "Acme.Editor.locale.en-US.yaml": {
                "PackageIdentifier": PACKAGE_ID,
                "PackageVersion": VERSION,
                "PackageLocale": "en-US",
                "PackageName": "Acme Editor",
                "Publisher": "Acme Inc",
                **({"PublisherUrl": publisher_url} if publisher_url else {}),
                "ManifestType": "defaultLocale",
                "ManifestVersion": "1.10.0",
            },
            "Acme.Editor.installer.yaml": {
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
        elif path.startswith("repos/acme/editor/releases/tags/"):
            payload = {"message": "Not Found"}
        elif path.endswith("/Acme/Editor"):
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
            encoded = base64.b64encode(raw).decode()
            if self.wrap_base64:
                encoded = "\n".join(
                    encoded[index:index + 60]
                    for index in range(0, len(encoded), 60)
                )
            payload = {"encoding": "base64", "content": encoded}
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
    assert result.candidate.publisher == "Acme Inc"
    assert result.candidate.installer_domain == "github.com"
    assert result.candidate.installer_sha256 == "b" * 64
    assert result.candidate.publisher_verification == "NOT_CHECKED"
    assert result.candidate.official_version is None
    assert result.candidate.official_asset_id is None
    assert "publisher_official_source_not_yet_cross_checked" in result.candidate.limitations
    assert "installer_authenticode_signature_not_yet_verified" in result.candidate.limitations
    assert all(call[1]["allow_redirects"] is False for call in source.calls)
    assert all("winget.exe" not in call[0] for call in source.calls)
    assert any(
        "/contents/manifests/a/Acme/Editor" in call[0]
        for call in source.calls
    )



def test_generic_github_publisher_release_is_discovered_from_manifest_publisher_url():
    source = FakeSource(publisher_url="https://github.com/acme/editor")
    original_get = source.get

    def with_release(url, **kwargs):
        if request_path(url) == "repos/acme/editor/releases/tags/" + VERSION:
            source.calls.append((url, kwargs))
            return FakeResponse({
                "tag_name": VERSION,
                "html_url": "https://github.com/acme/editor/releases/tag/" + VERSION,
                "assets": [{
                    "id": 101,
                    "browser_download_url": (
                        "https://github.com/acme/editor/releases/download/"
                        + VERSION + "/acme-editor-" + VERSION + "-windows-x86_64.exe"
                    ),
                    "digest": "sha256:" + "b" * 64,
                }],
            })
        return original_get(url, **kwargs)

    result = WinGetManifestRepository(http_get=with_release).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "CONDITIONAL"
    assert result.candidate is not None
    assert result.candidate.publisher_verification == "VERIFIED"
    assert result.candidate.publisher_url == "https://github.com/acme/editor"
    assert result.candidate.official_version == VERSION
    assert result.candidate.official_asset_sha256 == "b" * 64
    assert result.candidate.official_asset_id == 101
    release_calls = [call for call in source.calls if "api.github.com/repos/acme/editor/releases/tags/" in call[0]]
    assert len(release_calls) == 1
    assert release_calls[0][1]["allow_redirects"] is False


def test_generic_github_publisher_release_hash_mismatch_fails_closed_for_candidate():
    source = FakeSource(publisher_url="https://github.com/acme/editor")
    original_get = source.get

    def with_wrong_release_hash(url, **kwargs):
        if request_path(url) == "repos/acme/editor/releases/tags/" + VERSION:
            return FakeResponse({
                "tag_name": VERSION,
                "html_url": "https://github.com/acme/editor/releases/tag/" + VERSION,
                "assets": [{
                    "id": 101,
                    "browser_download_url": (
                        "https://github.com/acme/editor/releases/download/"
                        + VERSION + "/acme-editor-" + VERSION + "-windows-x86_64.exe"
                    ),
                    "digest": "sha256:" + "c" * 64,
                }],
            })
        return original_get(url, **kwargs)

    result = WinGetManifestRepository(http_get=with_wrong_release_hash).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "SOURCE_MISMATCH"
    assert result.candidate is not None
    assert result.candidate.publisher_verification == "MISMATCH"


def test_non_github_publisher_url_uses_generic_manifest_hash_policy_without_hardcoded_lookup():
    source = FakeSource(publisher_url="https://www.acme.example")
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "CONDITIONAL"
    assert result.candidate is not None
    assert result.candidate.publisher_verification == "NOT_CHECKED"
    assert not any("api.github.com/repos/" in call[0] for call in source.calls)


@pytest.mark.parametrize("manifest_type", ["nullsoft", "inno", "burn"])
def test_discovery_normalizes_executable_installer_technologies_for_any_package(manifest_type):
    source = FakeSource()
    installer_doc = source.documents["Acme.Editor.installer.yaml"]
    installer_doc["Installers"][0]["InstallerType"] = manifest_type
    installer_doc["Installers"][0]["InstallerUrl"] = "https://downloads.acme.example/editor-setup.exe"

    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.candidate is not None
    assert result.candidate.package_id == PACKAGE_ID
    assert result.candidate.installer_type == "exe"
    assert result.candidate.installer_technology == manifest_type
    assert result.candidate.installer_silent_switch == "/S"


def test_discovery_preserves_custom_switches_and_installer_success_codes():
    source = FakeSource()
    installer = source.documents["Acme.Editor.installer.yaml"]["Installers"][0]
    installer["InstallerType"] = "nullsoft"
    installer["InstallerSwitches"] = {
        "Custom": "/currentuser",
    }
    installer["InstallerSuccessCodes"] = [3010]
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )
    assert result.candidate is not None
    assert result.candidate.installer_technology == "nullsoft"
    assert result.candidate.installer_silent_switch is None
    assert result.candidate.installer_silent_with_progress_switch is None
    assert result.candidate.installer_custom_switch == "/currentuser"
    assert result.candidate.installer_success_codes == (3010,)


def test_discovery_inherits_user_scope_declared_at_installer_manifest_level():
    source = FakeSource()
    installer_doc = source.documents["Acme.Editor.installer.yaml"]
    installer_doc["Scope"] = "user"
    del installer_doc["Installers"][0]["Scope"]
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )
    assert result.candidate is not None
    assert result.candidate.scope == "user"



def test_discovery_accepts_whitespace_wrapped_github_base64_manifest_content():
    source = FakeSource(wrap_base64=True)
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )
    assert result.candidate is not None
    assert result.candidate.package_id == PACKAGE_ID


def test_discovery_offers_manifest_versions_when_official_release_source_is_unavailable():
    source = FakeSource(publisher_url="https://github.com/acme/editor")
    original_get = source.get

    def unavailable_releases(url, **kwargs):
        if request_path(url).startswith("repos/acme/editor/releases/"):
            return FakeResponse({}, status_code=503)
        return original_get(url, **kwargs)

    result = WinGetManifestRepository(http_get=unavailable_releases).discover(
        package_id=PACKAGE_ID,
        version=None,
        architecture="x64",
    )

    assert result.status == "VERSION_REQUIRED"
    assert result.official_versions is None
    assert result.available_versions == (VERSION,)
    assert result.manifest_versions == (VERSION,)


def test_selected_version_continues_when_optional_official_release_check_is_unavailable():
    source = FakeSource(publisher_url="https://github.com/acme/editor")
    original_get = source.get

    def unavailable_selected_release(url, **kwargs):
        if request_path(url).startswith("repos/acme/editor/releases/tags/"):
            return FakeResponse({}, status_code=503)
        return original_get(url, **kwargs)

    result = WinGetManifestRepository(http_get=unavailable_selected_release).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "CONDITIONAL"
    assert result.candidate is not None
    assert result.candidate.publisher_verification == "NOT_CHECKED"
    assert result.candidate.official_version is None


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
    assert result.manifest_versions == (VERSION,)
    assert result.official_versions is None


@pytest.mark.parametrize(
    "source",
    [
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


def test_discovery_inherits_root_level_silent_switch_for_selected_installer():
    source = FakeSource()
    installer_doc = source.documents["Acme.Editor.installer.yaml"]
    installer_doc["InstallerSwitches"] = {"Silent": "/S"}
    del installer_doc["Installers"][0]["InstallerSwitches"]
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )
    assert result.candidate is not None
    assert result.candidate.installer_silent_switch == "/S"


def test_discovery_rejects_selected_installer_dependencies_not_in_exact_approval():
    source = FakeSource()
    source.documents["Acme.Editor.installer.yaml"]["Installers"][0]["Dependencies"] = {
        "PackageDependencies": [{"PackageIdentifier": "Microsoft.VCRedist.2015+.x64"}]
    }

    with pytest.raises(DiscoveryUnavailable, match="selected installer dependencies"):
        WinGetManifestRepository(http_get=source.get).discover(
            package_id=PACKAGE_ID,
            version=VERSION,
            architecture="x64",
        )


def test_discovery_rejects_package_dependencies_not_in_exact_approval():
    source = FakeSource()
    source.documents["Acme.Editor.installer.yaml"]["Dependencies"] = {
        "PackageDependencies": [{
            "PackageIdentifier": "Microsoft.VCRedist.2015+.x64",
        }]
    }

    with pytest.raises(DiscoveryUnavailable, match="package dependencies"):
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
            if request_path(url).endswith("/Acme/Editor"):
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

    manifest_calls = [
        call for call in source.calls
        if "/repos/microsoft/winget-pkgs/" in call[0]
    ]
    assert manifest_calls
    assert all(
        call[0].startswith("https://api.github.com/repos/microsoft/winget-pkgs/")
        for call in manifest_calls
    )
    pinned_manifest_calls = [
        call for call in manifest_calls
        if "commits/master" not in call[0]
    ]
    assert all(call[1]["params"]["ref"] == COMMIT for call in pinned_manifest_calls)
    # Discovery is intentionally independent of vendor-specific release APIs.
    assert all("releases/tags" not in call[0] for call in source.calls)




def test_manifest_source_retries_transient_server_errors_and_uses_actions_token(monkeypatch):
    source = FakeSource()
    attempts = 0

    def flaky_get(url, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeResponse({}, status_code=503)
        return source.get(url, **kwargs)

    monkeypatch.setenv("GITHUB_TOKEN", "read-only-actions-token")
    result = WinGetManifestRepository(http_get=flaky_get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.candidate is not None
    assert attempts > len(source.calls)
    manifest_calls = [
        call for call in source.calls if "/repos/microsoft/winget-pkgs/" in call[0]
    ]
    assert manifest_calls
    assert all(
        call[1]["headers"]["Authorization"] == "Bearer read-only-actions-token"
        for call in manifest_calls
    )


def test_discovery_unavailable_preserves_upstream_http_status(monkeypatch):
    monkeypatch.setattr("agent_backend.software_discovery.time.sleep", lambda _delay: None)

    class UnavailableResponse(FakeResponse):
        def __init__(self, status_code):
            super().__init__({}, status_code=status_code)

    repository = WinGetManifestRepository(
        http_get=lambda *_args, **_kwargs: UnavailableResponse(503)
    )

    with pytest.raises(DiscoveryUnavailable) as captured:
        repository._get_json("/repos/microsoft/winget-pkgs/commits/master")

    assert captured.value.upstream_status == 503
    assert captured.value.failure_code == "upstream_http_error"


def test_discovery_not_found_preserves_upstream_404(monkeypatch):
    monkeypatch.setattr("agent_backend.software_discovery.time.sleep", lambda _delay: None)

    class NotFoundResponse(FakeResponse):
        def __init__(self):
            super().__init__({}, status_code=404)

    repository = WinGetManifestRepository(
        http_get=lambda *_args, **_kwargs: NotFoundResponse()
    )

    with pytest.raises(DiscoveryNotFound) as captured:
        repository._get_json("/repos/microsoft/winget-pkgs/commits/master")

    assert captured.value.upstream_status == 404



def test_discovery_reports_safe_scope_choices_without_implicitly_selecting_machine():
    source = FakeSource(bad_scope=True)
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "SCOPE_REQUIRED"
    assert result.candidate is None
    assert result.available_scopes == ("machine",)

def test_version_listing_uses_one_numeric_order_and_limit_for_every_package():
    class VersionListingSource(FakeSource):
        def __init__(self):
            super().__init__()

        def get(self, url, **kwargs):
            if request_path(url).endswith("/Acme/Editor"):
                versions = [f"{major}.0.0" for major in range(1, 26)]
                versions.extend([VERSION, "26.0.0", "26.1.0", "26.2.5", "26.2.6-beta", "CN"])
                return FakeResponse([
                    {"name": version, "type": "dir"} for version in versions
                ])
            return super().get(url, **kwargs)

    result = WinGetManifestRepository(
        http_get=VersionListingSource().get
    ).discover(
        package_id=PACKAGE_ID,
        version=None,
        architecture="x64",
    )

    assert result.status == "VERSION_REQUIRED"
    assert len(result.manifest_versions) == 20
    # The fixture contains 30 distinct valid versions; the newest-20 window starts at 11.0.0.
    assert result.manifest_versions[0] == "11.0.0"
    assert result.available_versions == result.manifest_versions
    assert result.manifest_versions[-1] == "26.2.6-beta"
    assert "25.3.0" in result.manifest_versions
    assert "CN" not in result.manifest_versions

    selected = WinGetManifestRepository(
        http_get=VersionListingSource().get
    ).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )
    assert selected.available_versions == result.manifest_versions



def test_discovery_accepts_manifest_filenames_containing_plus_signs():
    plus_package_id = PACKAGE_ID.replace("Acme", "Acme++")

    class PlusFilenameSource(FakeSource):
        def __init__(self):
            super().__init__()
            self.documents = {
                name.replace("Acme", "Acme++"): {
                    **document,
                    "PackageIdentifier": plus_package_id,
                }
                for name, document in self.documents.items()
            }

        def get(self, url, **kwargs):
            path = request_path(url).replace(
                "/Acme++/Editor",
                "/Acme/Editor",
            )
            if path != request_path(url):
                url = url.replace(
                    "/Acme++/Editor",
                    "/Acme/Editor",
                )
            return super().get(url, **kwargs)

    result = WinGetManifestRepository(
        http_get=PlusFilenameSource().get
    ).discover(
        package_id=plus_package_id,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "CONDITIONAL"
    assert result.candidate is not None
    assert result.candidate.package_id == plus_package_id


def test_discovery_accepts_yaml_file_entries_with_missing_optional_type_metadata():
    class IncompleteMetadataSource(FakeSource):
        def get(self, url, **kwargs):
            response = super().get(url, **kwargs)
            if request_path(url).endswith(f"/manifests/a/Acme/Editor/{VERSION}"):
                entries = json.loads(response._body)
                for entry in entries:
                    entry.pop("type", None)
                response._body = json.dumps(entries).encode()
            return response

    result = WinGetManifestRepository(
        http_get=IncompleteMetadataSource().get
    ).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.candidate is not None
    assert result.candidate.package_id == PACKAGE_ID


def test_discovery_rejects_manifest_listing_with_no_safe_yaml_files():
    class UnsafeListingSource(FakeSource):
        def get(self, url, **kwargs):
            if request_path(url).endswith(f"/{VERSION}"):
                return FakeResponse([
                    {"name": "../manifest.yaml", "type": "file"},
                    {"name": "manifest.txt", "type": "file"},
                    {"name": "directory.yaml", "type": "dir"},
                ])
            return super().get(url, **kwargs)

    with pytest.raises(DiscoveryUnavailable) as captured:
        WinGetManifestRepository(
            http_get=UnsafeListingSource().get
        ).discover(
            package_id=PACKAGE_ID,
            version=VERSION,
            architecture="x64",
        )

    assert captured.value.failure_code == "manifest_file_set_empty"
    assert captured.value.diagnostic_fields["manifest_listing_item_count"] == 3
    assert captured.value.diagnostic_fields["manifest_yaml_file_count"] == 0

def test_discovery_can_explicitly_enumerate_machine_scope_without_authorizing_installation():
    source = FakeSource(bad_scope=True)
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
        scope="machine",
    )

    assert result.status == "CONDITIONAL"
    assert result.available_scopes == ("machine",)
    assert result.candidate is not None
    assert result.candidate.scope == "machine"

def test_discovery_returns_available_scope_choices_when_user_scope_is_missing():
    source = FakeSource(bad_scope=True)
    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
    )

    assert result.status == "SCOPE_REQUIRED"
    assert result.candidate is None
    assert result.available_scopes == ("machine",)


def test_discovery_uses_winget_default_installer_type_priority_for_multiple_matches():
    source = FakeSource()
    installer_doc = source.documents["Acme.Editor.installer.yaml"]
    first = installer_doc["Installers"][0]
    first.update({
        "InstallerType": "nullsoft",
        "InstallerUrl": "https://downloads.acme.example/editor-setup.exe",
        "InstallerSha256": "c" * 64,
    })
    second = {
        "Architecture": "x64",
        "Scope": "user",
        "InstallerType": "wix",
        "InstallerUrl": "https://downloads.acme.example/editor-setup.msi",
        "InstallerSha256": "d" * 64,
    }
    installer_doc["Installers"] = [first, second]

    result = WinGetManifestRepository(http_get=source.get).discover(
        package_id=PACKAGE_ID,
        version=VERSION,
        architecture="x64",
        scope="user",
    )

    assert result.candidate is not None
    assert result.candidate.installer_technology == "wix"
    assert result.candidate.installer_type == "msi"
    assert result.candidate.installer_url.endswith("editor-setup.msi")
    assert result.candidate.installer_sha256 == "d" * 64
