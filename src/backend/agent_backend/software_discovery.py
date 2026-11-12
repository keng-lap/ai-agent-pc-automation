"""Read-only WinGet manifest discovery with fail-closed trust classification.

This module reads the Microsoft-owned winget-pkgs repository over its fixed
GitHub API origin. It never invokes WinGet, downloads installers, or executes
package code. A manifest match is only a CONDITIONAL candidate until publisher
ownership and the downloaded installer's Authenticode signature are verified.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import requests
import yaml
from pydantic import BaseModel, ConfigDict, Field
from yaml.tokens import AliasToken, AnchorToken


WINGET_REPOSITORY = "microsoft/winget-pkgs"
GITHUB_API_ORIGIN = "https://api.github.com"
USER_AGENT = "ai-agent-pc-automation-trusted-discovery/1.0"
MAX_RESPONSE_BYTES = 1_000_000
MAX_MANIFEST_FILES = 12
PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class DiscoveryError(RuntimeError):
    """A bounded, safe discovery failure."""


class DiscoveryNotFound(DiscoveryError):
    """The requested package or version is not present in the source."""


class DiscoveryUnavailable(DiscoveryError):
    """The approved source could not be reached or parsed safely."""


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
    installer_url: str
    installer_domain: str
    installer_sha256: str
    manifest_sha256: str
    repository_commit: str
    manifest_source_url: str
    checked_at: str
    status: Literal["CONDITIONAL"] = "CONDITIONAL"
    limitations: tuple[str, ...] = (
        "publisher_official_source_not_yet_cross_checked",
        "installer_authenticode_signature_not_yet_verified",
    )


class DiscoveryResponse(BaseModel):
    """A discovery result that cannot be mistaken for verified approval evidence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    status: Literal["VERSION_REQUIRED", "CONDITIONAL"]
    package_id: str
    available_versions: tuple[str, ...]
    candidate: InstallerCandidate | None = None
    source: Literal["winget-community-repository"] = "winget-community-repository"


class WinGetManifestRepository:
    """Read exact package manifests from Microsoft's official GitHub repository."""

    def __init__(self, *, http_get=None, clock=None) -> None:
        self._http_get = http_get or requests.get
        self._clock = clock or _utc_now_iso

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
                }
            )
        )
        if not versions:
            raise DiscoveryNotFound("package has no published manifest versions")
        if version is None:
            return DiscoveryResponse(
                status="VERSION_REQUIRED",
                package_id=normalized_id,
                available_versions=versions[-20:],
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
        yaml_files = [
            item
            for item in files
            if isinstance(item, dict)
            and item.get("type") == "file"
            and isinstance(item.get("name"), str)
            and re.fullmatch(r"[A-Za-z0-9._-]{1,200}\.ya?ml", item["name"], re.IGNORECASE)
        ]
        if not yaml_files or len(yaml_files) > MAX_MANIFEST_FILES:
            raise DiscoveryUnavailable("manifest file set was empty or exceeded its limit")

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
                raw = base64.b64decode(content_response["content"], validate=True)
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
        if (
            len(manifest_versions) != 1
            or not isinstance(next(iter(manifest_versions)), str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", next(iter(manifest_versions)))
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
        matching = [
            item
            for item in installers
            if isinstance(item, dict)
            and item.get("Architecture") == architecture
            and isinstance(item.get("Scope"), str)
            and item["Scope"].lower() == "user"
        ]
        if len(matching) != 1:
            raise DiscoveryUnavailable(
                "manifest must contain exactly one installer for the requested architecture and user scope"
            )
        installer = matching[0]
        installer_url = installer.get("InstallerUrl")
        installer_hash = installer.get("InstallerSha256")
        installer_type = installer.get("InstallerType") or installer_doc.get("InstallerType")
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
        candidate = InstallerCandidate(
            package_id=normalized_id,
            package_name=package_name,
            publisher=publisher,
            version=version,
            architecture=architecture,
            scope="user",
            installer_type=installer_type,
            installer_url=installer_url,
            installer_domain=domain,
            installer_sha256=installer_hash.lower(),
            manifest_sha256=manifest_hash.hexdigest(),
            repository_commit=commit_sha,
            manifest_source_url=source_url,
            checked_at=self._clock(),
        )
        return DiscoveryResponse(
            status="CONDITIONAL",
            package_id=normalized_id,
            available_versions=versions,
            candidate=candidate,
        )

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        if not path.startswith("/repos/microsoft/winget-pkgs/"):
            raise DiscoveryUnavailable("request path is outside the approved source")
        url = GITHUB_API_ORIGIN + path
        response = None
        try:
            response = self._http_get(
                url,
                params=params,
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
                raise DiscoveryNotFound("package or manifest was not found in the approved source")
            if response.status_code != 200:
                raise DiscoveryUnavailable("approved package source returned an unsuccessful response")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise DiscoveryUnavailable("approved source response exceeded its size limit")
                chunks.append(chunk)
            return json.loads(b"".join(chunks))
        except (DiscoveryNotFound, DiscoveryUnavailable):
            raise
        except (requests.RequestException, ValueError, TypeError):
            raise DiscoveryUnavailable("approved package source could not be read safely") from None
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()


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
