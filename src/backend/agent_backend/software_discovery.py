"""Read-only WinGet manifest discovery with fail-closed trust classification.

This module reads the Microsoft-owned winget-pkgs repository over its fixed
GitHub API origin. It never invokes WinGet, downloads installers, or executes
package code. A manifest match is only a CONDITIONAL candidate until the downloaded installer's
Authenticode chain and signer identity are verified against the manifest Publisher.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import time
from typing import Any, Literal
from urllib.parse import urlsplit

import requests
import yaml
from pydantic import BaseModel, ConfigDict
from yaml.tokens import AliasToken, AnchorToken

WINGET_REPOSITORY = "microsoft/winget-pkgs"
GITHUB_API_ORIGIN = "https://api.github.com"
USER_AGENT = "ai-agent-pc-automation-trusted-discovery/1.0"
MAX_RESPONSE_BYTES = 1_000_000
MAX_MANIFEST_FILES = 12
MAX_AVAILABLE_VERSIONS = 20
MAX_OFFICIAL_RELEASES = 100
PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class DiscoveryError(RuntimeError):
    """A bounded, safe discovery failure."""


class DiscoveryNotFound(DiscoveryError):
    """The requested package or version is not present in the source."""

    def __init__(self, message: str, *, upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status


class DiscoveryUnavailable(DiscoveryError):
    """The approved source could not be reached or parsed safely."""

    def __init__(
        self,
        message: str,
        *,
        upstream_status: int | None = None,
        failure_code: str = "source_unavailable",
        diagnostic_fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.upstream_status = upstream_status
        self.failure_code = failure_code
        self.diagnostic_fields = diagnostic_fields or {}


class InstallerCandidate(BaseModel):
    """Manifest facts; these fields are not an execution authorization."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str
    package_name: str
    publisher: str
    version: str
    architecture: Literal["x86", "x64", "arm64"]
    scope: Literal["user"]
    installer_type: str
    installer_silent_switch: str | None = None
    installer_url: str
    installer_domain: str
    installer_sha256: str
    manifest_sha256: str
    repository_commit: str
    manifest_source_url: str
    checked_at: str
    publisher_verification: Literal["NOT_CHECKED", "VERIFIED", "MISMATCH", "UNAVAILABLE"] = "NOT_CHECKED"
    official_version: str | None = None
    official_release_url: str | None = None
    official_asset_sha256: str | None = None
    official_asset_id: int | None = None
    status: Literal["CONDITIONAL"] = "CONDITIONAL"
    limitations: tuple[str, ...] = (
        "publisher_official_source_not_yet_cross_checked",
        "installer_authenticode_signature_not_yet_verified",
    )


class PublisherVerification(BaseModel):
    """Result of comparing a manifest candidate with a vendor-controlled release."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["NOT_CHECKED", "VERIFIED", "MISMATCH", "UNAVAILABLE"]
    official_version: str | None = None
    official_release_url: str | None = None
    official_asset_sha256: str | None = None
    official_asset_id: int | None = None


class DBeaverGitHubReleaseVerifier:
    """Cross-check DBeaver Community manifests against its official GitHub release."""

    RELEASES_API_URL = "https://api.github.com/repos/dbeaver/dbeaver/releases?per_page=10"
    RELEASES_PAGE_SIZE = 10
    RELEASE_TAG_API_PREFIX = "https://api.github.com/repos/dbeaver/dbeaver/releases/tags/"
    RELEASE_PAGE_PREFIX = "https://github.com/dbeaver/dbeaver/releases/tag/"
    ASSET_PREFIX = "https://github.com/dbeaver/dbeaver/releases/download/"

    def __init__(self, *, http_get=None) -> None:
        self._http_get = http_get or requests.get

    def list_official_versions(self, package_id: str) -> tuple[str, ...] | None:
        """Return up to 20 stable releases using bounded pagination.

        Each page is small, the combined payload has a strict byte limit, and
        pagination stops as soon as enough stable versions are collected.
        """
        if package_id != "DBeaver.DBeaver.Community":
            return None
        versions: list[str] = []
        total_bytes = 0
        for page in range(1, (MAX_OFFICIAL_RELEASES // self.RELEASES_PAGE_SIZE) + 1):
            response = None
            try:
                response = self._http_get(
                    self.RELEASES_API_URL,
                    params={"page": str(page)},
                    headers={
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=(3.05, 10),
                    allow_redirects=False,
                    stream=True,
                )
                if response.status_code != 200:
                    return None
                chunks: list[bytes] = []
                page_bytes = 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    page_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > MAX_RESPONSE_BYTES:
                        return None
                    chunks.append(chunk)
                releases = json.loads(b"".join(chunks))
                if not isinstance(releases, list) or len(releases) > self.RELEASES_PAGE_SIZE:
                    return None
                for release in releases:
                    if not isinstance(release, dict):
                        return None
                    draft = release.get("draft")
                    prerelease = release.get("prerelease")
                    if type(draft) is not bool or type(prerelease) is not bool:
                        return None
                    if draft or prerelease:
                        continue
                    tag = release.get("tag_name")
                    url = release.get("html_url")
                    if (
                        not isinstance(tag, str)
                        or not VERSION_PATTERN.fullmatch(tag)
                        or url != self.RELEASE_PAGE_PREFIX + tag
                    ):
                        return None
                    versions.append(tag)
                if len(releases) < self.RELEASES_PAGE_SIZE:
                    break
                if len(set(versions)) >= MAX_AVAILABLE_VERSIONS:
                    break
            except (requests.RequestException, ValueError, TypeError, KeyError):
                return None
            finally:
                if response is not None:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
        return tuple(sorted(set(versions), key=_version_sort_key)[-MAX_AVAILABLE_VERSIONS:])

    def verify(
        self,
        *,
        package_id: str,
        publisher: str,
        version: str,
        architecture: str,
        installer_url: str,
        installer_sha256: str,
    ) -> PublisherVerification:
        if package_id != "DBeaver.DBeaver.Community":
            return PublisherVerification(status="NOT_CHECKED")
        if publisher.strip().casefold() != "dbeaver corp":
            return PublisherVerification(status="MISMATCH")

        # Verify the exact selected tag directly. The version-list endpoint is
        # only for UI choices; pagination/truncation must never substitute the
        # latest release for the operator's selected version.
        response = None
        try:
            response = self._http_get(
                self.RELEASE_TAG_API_PREFIX + version,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": USER_AGENT,
                },
                timeout=(3.05, 10),
                allow_redirects=False,
                stream=True,
            )
            if response.status_code == 404:
                return PublisherVerification(status="MISMATCH")
            if response.status_code != 200:
                return PublisherVerification(status="UNAVAILABLE")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    return PublisherVerification(status="UNAVAILABLE")
                chunks.append(chunk)
            release = json.loads(b"".join(chunks))
            if not isinstance(release, dict):
                return PublisherVerification(status="UNAVAILABLE")
            official_version = release.get("tag_name")
            release_url = release.get("html_url")
            if (
                not isinstance(official_version, str)
                or not VERSION_PATTERN.fullmatch(official_version)
                or release_url != self.RELEASE_PAGE_PREFIX + official_version
            ):
                return PublisherVerification(status="UNAVAILABLE")
            if release.get("draft") is not False or release.get("prerelease") is not False:
                return PublisherVerification(
                    status="MISMATCH",
                    official_version=official_version,
                    official_release_url=release_url,
                )

            asset_name_by_architecture = {
                "x64": f"dbeaver-ce-{official_version}-windows-x86_64.exe",
                "arm64": f"dbeaver-ce-{official_version}-windows-aarch64.exe",
            }
            expected_asset_name = asset_name_by_architecture.get(architecture)
            if expected_asset_name is None:
                return PublisherVerification(
                    status="MISMATCH",
                    official_version=official_version,
                    official_release_url=release_url,
                )
            assets = release.get("assets")
            if not isinstance(assets, list) or len(assets) > 100:
                return PublisherVerification(status="UNAVAILABLE")
            matching_assets = [
                asset
                for asset in assets
                if isinstance(asset, dict)
                and asset.get("name") == expected_asset_name
                and isinstance(asset.get("browser_download_url"), str)
                and asset.get("browser_download_url")
                == self.ASSET_PREFIX + official_version + "/" + expected_asset_name
                and type(asset.get("id")) is int
                and asset.get("id") > 0
            ]
            if len(matching_assets) != 1:
                return PublisherVerification(
                    status="MISMATCH",
                    official_version=official_version,
                    official_release_url=release_url,
                )
            digest = matching_assets[0].get("digest")
            if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
                return PublisherVerification(status="UNAVAILABLE")
            official_sha256 = digest.split(":", 1)[1].lower()
            asset_url = matching_assets[0]["browser_download_url"]
            asset_id = matching_assets[0]["id"]
            if (
                version != official_version
                or installer_url != asset_url
                or installer_sha256.lower() != official_sha256
            ):
                return PublisherVerification(
                    status="MISMATCH",
                    official_version=official_version,
                    official_release_url=release_url,
                    official_asset_sha256=official_sha256,
                    official_asset_id=asset_id,
                )
            return PublisherVerification(
                status="VERIFIED",
                official_version=official_version,
                official_release_url=release_url,
                official_asset_sha256=official_sha256,
                official_asset_id=asset_id,
            )
        except (requests.RequestException, ValueError, TypeError, KeyError):
            return PublisherVerification(status="UNAVAILABLE")
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()


class DiscoveryResponse(BaseModel):
    """A discovery result that cannot be mistaken for verified approval evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["VERSION_REQUIRED", "CONDITIONAL", "SOURCE_MISMATCH", "SOURCE_CHECK_UNAVAILABLE"]
    package_id: str
    available_versions: tuple[str, ...]
    manifest_versions: tuple[str, ...] = ()
    official_versions: tuple[str, ...] | None = None
    candidate: InstallerCandidate | None = None
    source: Literal["winget-community-repository"] = "winget-community-repository"


class WinGetManifestRepository:
    """Read exact package manifests from Microsoft's official GitHub repository."""

    def __init__(self, *, http_get=None, clock=None, publisher_verifier=None) -> None:
        self._http_get = http_get or requests.get
        self._clock = clock or _utc_now_iso
        self._publisher_verifier = publisher_verifier or DBeaverGitHubReleaseVerifier(http_get=self._http_get)

    def discover(
        self,
        *,
        package_id: str,
        version: str | None,
        architecture: Literal["x86", "x64", "arm64"],
    ) -> DiscoveryResponse:
        normalized_id = _validate_package_id(package_id)
        if version is not None and not VERSION_PATTERN.fullmatch(version):
            raise ValueError("version contains unsupported characters")

        commit = self._get_json(
            f"/repos/{WINGET_REPOSITORY}/commits/master"
        )
        commit_sha = commit.get("sha") if isinstance(commit, dict) else None
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise DiscoveryUnavailable("source revision response was invalid")

        manifest_root = _manifest_package_path(normalized_id)
        version_entries = self._get_json(
            f"/repos/{WINGET_REPOSITORY}/contents/{manifest_root}",
            params={"ref": commit_sha},
        )
        if not isinstance(version_entries, list):
            raise DiscoveryUnavailable("package version listing was invalid")

        versions = tuple(
            sorted(
                {
                    item["name"]
                    for item in version_entries
                    if isinstance(item, dict)
                    and item.get("type") == "dir"
                    and isinstance(item.get("name"), str)
                    and VERSION_PATTERN.fullmatch(item["name"])
                },
                key=_version_sort_key,
            )
        )
        if not versions:
            raise DiscoveryNotFound("package has no published manifest versions")
        if version is None:
            list_versions = getattr(self._publisher_verifier, "list_official_versions", None)
            official_versions = list_versions(normalized_id) if callable(list_versions) else None
            manifest_versions = versions[-MAX_AVAILABLE_VERSIONS:]
            selectable_versions = manifest_versions
            if normalized_id == "DBeaver.DBeaver.Community":
                selectable_versions = (
                    tuple(v for v in manifest_versions if v in set(official_versions))
                    if official_versions is not None else ()
                )
            return DiscoveryResponse(
                status="VERSION_REQUIRED",
                package_id=normalized_id,
                available_versions=selectable_versions,
                manifest_versions=manifest_versions,
                official_versions=official_versions,
            )
        if version not in versions:
            raise DiscoveryNotFound("requested package version was not found")

        version_path = f"{manifest_root}/{version}"
        files = self._get_json(
            f"/repos/{WINGET_REPOSITORY}/contents/{version_path}",
            params={"ref": commit_sha},
        )
        if not isinstance(files, list):
            raise DiscoveryUnavailable("manifest file listing was invalid")
        valid_named_files = [
            item
            for item in files
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and re.fullmatch(r"[A-Za-z0-9.+_-]{1,200}\.ya?ml", item["name"], re.IGNORECASE)
        ]
        # GitHub's Contents API normally returns type="file". A missing type
        # is incomplete metadata, not proof that a safe YAML filename is not
        # a file; the pinned Contents request below still validates base64
        # content and the parsed manifest schema before use.
        yaml_files = [
            item for item in valid_named_files
            if item.get("type") is None
            or (isinstance(item.get("type"), str) and item["type"].casefold() == "file")
        ]
        listing_summary = ";".join(
            f"{'file' if item.get('type') is not None else 'missing'}:{item['name'][:200]}"
            for item in yaml_files[:8]
        )[:240]
        listing_fields = {
            "manifest_listing_item_count": len(files),
            "manifest_named_yaml_count": len(valid_named_files),
            "manifest_yaml_file_count": len(yaml_files),
            "manifest_listing_summary": listing_summary,
        }
        if not yaml_files:
            raise DiscoveryUnavailable(
                "manifest file listing contained no acceptable YAML files",
                failure_code="manifest_file_set_empty",
                diagnostic_fields=listing_fields,
            )
        if len(yaml_files) > MAX_MANIFEST_FILES:
            raise DiscoveryUnavailable(
                "manifest file listing exceeded its safety limit",
                failure_code="manifest_file_set_exceeds_limit",
                diagnostic_fields=listing_fields,
            )

        documents: list[tuple[str, bytes, dict[str, Any]]] = []
        for item in sorted(yaml_files, key=lambda value: value["name"]):
            content_response = self._get_json(
                f"/repos/{WINGET_REPOSITORY}/contents/{version_path}/{item['name']}",
                params={"ref": commit_sha},
            )
            if (
                not isinstance(content_response, dict)
                or content_response.get("encoding") != "base64"
                or not isinstance(content_response.get("content"), str)
            ):
                raise DiscoveryUnavailable("manifest content response was invalid")
            try:
                encoded_content = "".join(content_response["content"].split())
                raw = base64.b64decode(encoded_content, validate=True)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise DiscoveryUnavailable("manifest document exceeded its size limit")
                if any(isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(raw)):
                    raise DiscoveryUnavailable("YAML anchors and aliases are not accepted")
                document = yaml.safe_load(raw)
            except (ValueError, yaml.YAMLError):
                raise DiscoveryUnavailable("manifest content could not be decoded safely") from None
            if not isinstance(document, dict):
                raise DiscoveryUnavailable("manifest document must be a YAML mapping")
            documents.append((item["name"], raw, document))

        # This exact-action proposal approves one Package ID/version only.
        # Do not allow WinGet to add undeclared-by-the-approval dependency installs.
        if any(document.get("Dependencies") for _, _, document in documents):
            raise DiscoveryUnavailable(
                "package manifests with additional package dependencies are not eligible for exact single-package approval"
            )

        package_docs = [
            document
            for _, _, document in documents
            if "PackageIdentifier" in document and "DefaultLocale" in document
        ]
        installer_docs = [
            document
            for _, _, document in documents
            if "Installers" in document
        ]
        locale_docs = [
            document
            for _, _, document in documents
            if "PackageLocale" in document
        ]
        default_locale_docs = [
            document
            for document in locale_docs
            if document.get("ManifestType") == "defaultLocale"
        ]
        if (
            len(package_docs) != 1
            or len(installer_docs) != 1
            or len(default_locale_docs) != 1
        ):
            raise DiscoveryUnavailable(
                "manifest set did not contain exactly one version, installer and default locale document"
            )

        package_doc = package_docs[0]
        installer_doc = installer_docs[0]
        default_locale_doc = default_locale_docs[0]
        if (
            package_doc.get("ManifestType") != "version"
            or installer_doc.get("ManifestType") != "installer"
            or any(
                document.get("PackageIdentifier") != normalized_id
                or document.get("PackageVersion") != version
                for _, _, document in documents
            )
        ):
            raise DiscoveryUnavailable("manifest identity, type or version did not match the requested package")
        expected_file_names = {
            "version": f"{normalized_id}.yaml",
            "installer": f"{normalized_id}.installer.yaml",
        }
        for name, _, document in documents:
            manifest_type = document.get("ManifestType")
            if manifest_type in expected_file_names:
                if name != expected_file_names[manifest_type]:
                    raise DiscoveryUnavailable("manifest filename did not match its declared type")
            elif manifest_type in {"defaultLocale", "locale"}:
                locale = document.get("PackageLocale")
                if (
                    not isinstance(locale, str)
                    or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", locale)
                    or name != f"{normalized_id}.locale.{locale}.yaml"
                ):
                    raise DiscoveryUnavailable("locale manifest filename did not match its locale")
            else:
                raise DiscoveryUnavailable("manifest contained an unsupported document type")

        manifest_versions = {
            document.get("ManifestVersion")
            for _, _, document in documents
        }
        manifest_version = next(iter(manifest_versions)) if len(manifest_versions) == 1 else None
        version_parts = manifest_version.split(".") if isinstance(manifest_version, str) else []
        if (
            len(version_parts) != 3
            or len(manifest_version) > 32
            or any(
                not part.isascii() or not part.isdigit() or len(part) > 8
                for part in version_parts
            )
        ):
            raise DiscoveryUnavailable("manifest schema versions were missing or inconsistent")

        default_locale = package_doc.get("DefaultLocale")
        if (
            not isinstance(default_locale, str)
            or not default_locale.strip()
            or default_locale_doc.get("PackageLocale") != default_locale
        ):
            raise DiscoveryUnavailable("manifest default locale did not match its locale document")
        package_name = _localized_value(default_locale_doc, "PackageName")
        publisher = _localized_value(default_locale_doc, "Publisher")
        if not package_name or not publisher:
            raise DiscoveryUnavailable("default locale did not contain a package name and publisher")

        installers = installer_doc.get("Installers")
        if not isinstance(installers, list):
            raise DiscoveryUnavailable("installer list was invalid")
        installer_facts = [
            item for item in installers if isinstance(item, dict)
        ]
        matching = [
            item
            for item in installer_facts
            if item.get("Architecture") == architecture
            and isinstance(item.get("Scope", installer_doc.get("Scope")), str)
            and item.get("Scope", installer_doc.get("Scope")).lower() == "user"
        ]
        if len(matching) != 1:
            available_architectures = sorted({
                item.get("Architecture")
                for item in installer_facts
                if isinstance(item.get("Architecture"), str)
            })
            available_scopes = sorted({
                item.get("Scope", installer_doc.get("Scope"))
                for item in installer_facts
                if isinstance(item.get("Scope", installer_doc.get("Scope")), str)
            })
            raise DiscoveryUnavailable(
                "manifest does not contain exactly one installer for the requested architecture and user scope",
                failure_code="installer_selection_not_unique",
                diagnostic_fields={
                    "requested_architecture": architecture,
                    "requested_scope": "user",
                    "installer_matching_count": len(matching),
                    "installer_architectures": ",".join(available_architectures),
                    "installer_scopes": ",".join(available_scopes),
                },
            )
        installer = matching[0]
        if installer.get("Dependencies"):
            raise DiscoveryUnavailable(
                "selected installer dependencies are not eligible for exact single-package approval"
            )
        installer_url = installer.get("InstallerUrl")
        installer_hash = installer.get("InstallerSha256")
        installer_type = installer.get("InstallerType") or installer_doc.get("InstallerType")
        switches = installer.get("InstallerSwitches")
        silent_switch = switches.get("Silent") if isinstance(switches, dict) else None
        if not silent_switch:
            root_switches = installer_doc.get("InstallerSwitches")
            silent_switch = root_switches.get("Silent") if isinstance(root_switches, dict) else None
        domain = _validate_installer_url(installer_url)
        if not isinstance(installer_hash, str) or not SHA256_PATTERN.fullmatch(installer_hash):
            raise DiscoveryUnavailable("installer SHA-256 was missing or invalid")
        if not isinstance(installer_type, str) or not installer_type.strip():
            raise DiscoveryUnavailable("installer type was missing")

        manifest_hash = hashlib.sha256()
        for name, raw, _ in documents:
            manifest_hash.update(name.encode("utf-8"))
            manifest_hash.update(b"\0")
            manifest_hash.update(raw)
            manifest_hash.update(b"\0")

        source_url = (
            f"https://github.com/{WINGET_REPOSITORY}/tree/{commit_sha}/{version_path}"
        )
        publisher_check = self._publisher_verifier.verify(
            package_id=normalized_id,
            publisher=publisher,
            version=version,
            architecture=architecture,
            installer_url=installer_url,
            installer_sha256=installer_hash.lower(),
        )
        limitations = ["installer_authenticode_signature_not_yet_verified"]
        if publisher_check.status == "NOT_CHECKED":
            limitations.append("publisher_official_source_not_yet_cross_checked")
        elif publisher_check.status == "MISMATCH":
            limitations.append("publisher_official_release_mismatch")
        elif publisher_check.status == "UNAVAILABLE":
            limitations.append("publisher_official_release_check_unavailable")

        candidate = InstallerCandidate(
            package_id=normalized_id,
            package_name=package_name,
            publisher=publisher,
            version=version,
            architecture=architecture,
            scope="user",
            installer_type=installer_type.strip().casefold(),
            installer_silent_switch=silent_switch,
            installer_url=installer_url,
            installer_domain=domain,
            installer_sha256=installer_hash.lower(),
            manifest_sha256=manifest_hash.hexdigest(),
            repository_commit=commit_sha,
            manifest_source_url=source_url,
            checked_at=self._clock(),
            publisher_verification=publisher_check.status,
            official_version=publisher_check.official_version,
            official_release_url=publisher_check.official_release_url,
            official_asset_sha256=publisher_check.official_asset_sha256,
            official_asset_id=publisher_check.official_asset_id,
            limitations=tuple(limitations),
        )
        response_status = {
            "MISMATCH": "SOURCE_MISMATCH",
            "UNAVAILABLE": "SOURCE_CHECK_UNAVAILABLE",
        }.get(publisher_check.status, "CONDITIONAL")
        return DiscoveryResponse(
            status=response_status,
            package_id=normalized_id,
            available_versions=versions[-MAX_AVAILABLE_VERSIONS:],
            candidate=candidate,
        )

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        if not path.startswith("/repos/microsoft/winget-pkgs/"):
            raise DiscoveryUnavailable("request path is outside the approved source")
        url = GITHUB_API_ORIGIN + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
        }
        # Actions provides a short-lived, read-only token. Using it avoids
        # anonymous API rate limits on shared Windows runners.
        github_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        for attempt in range(3):
            response = None
            try:
                response = self._http_get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=(3.05, 10),
                    allow_redirects=False,
                    stream=True,
                )
                if response.status_code == 404:
                    raise DiscoveryNotFound(
                        "package or manifest was not found in the approved source",
                        upstream_status=404,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                if response.status_code != 200:
                    raise DiscoveryUnavailable(
                        "approved package source returned an unsuccessful response",
                        upstream_status=response.status_code,
                        failure_code="upstream_http_error",
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise DiscoveryUnavailable(
                            "approved source response exceeded its size limit",
                            upstream_status=response.status_code,
                            failure_code="response_too_large",
                        )
                    chunks.append(chunk)
                return json.loads(b"".join(chunks))
            except (DiscoveryNotFound, DiscoveryUnavailable):
                raise
            except (requests.RequestException, ValueError, TypeError):
                if attempt < 2:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise DiscoveryUnavailable("approved package source could not be read safely") from None
            finally:
                if response is not None:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()
        raise DiscoveryUnavailable("approved package source could not be read safely")


def _version_sort_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Sort dotted/alphanumeric versions by numeric components, not lexically."""
    parts = re.split(r"(\d+)", value.casefold())
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in parts
        if part
    )


def _manifest_package_path(package_id: str) -> str:
    segments = package_id.split(".")
    publisher, package_segments = segments[0], segments[1:]
    return "/".join(
        ("manifests", publisher[0].lower(), publisher, *package_segments)
    )


def _validate_package_id(value: str) -> str:
    if not isinstance(value, str) or not PACKAGE_ID_PATTERN.fullmatch(value):
        raise ValueError("package identifier is invalid")
    segments = value.split(".")
    if not 2 <= len(segments) <= 4 or any(
        not segment or len(segment) > 32 for segment in segments
    ):
        raise ValueError("package identifier must contain two to four valid segments")
    return value


def _validate_installer_url(value: Any) -> str:
    if not isinstance(value, str):
        raise DiscoveryUnavailable("installer URL was missing")
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise DiscoveryUnavailable("installer URL must be an absolute HTTPS URL")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None or parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise DiscoveryUnavailable("installer URL must not target an IP address or localhost")
    return parsed.hostname.lower()


def _localized_value(document: dict[str, Any], key: str) -> str | None:
    value = document.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
