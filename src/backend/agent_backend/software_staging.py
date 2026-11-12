"""Bounded installer staging; never launches or installs downloaded files."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import requests
from pydantic import BaseModel, ConfigDict

from agent_backend.software_catalog import WindowsMsixSignatureVerifier
from agent_backend.software_discovery import InstallerCandidate

MAX_INSTALLER_BYTES = 512 * 1024 * 1024
CHUNK_SIZE = 65536
ALLOWED_INSTALLER_SUFFIXES = frozenset({".exe", ".msi", ".msix", ".appx"})
USER_AGENT = "ai-agent-pc-automation/0.1"


class InstallerStageError(RuntimeError):
    """A bounded download or verification step failed."""


class StagedInstaller(BaseModel):
    """Metadata for a staged file; the file has not been executed."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    package_id: str
    version: str
    architecture: Literal["x86", "x64", "arm64"]
    file_path: str
    file_size: int
    sha256: str
    authenticode_valid: Literal[True] = True
    # WinVerifyTrust currently returns only a trust result, not the signer subject.
    # Keep this unset until a verifier can extract and validate the signer identity.
    signature_subject: str | None = None
    official_release_url: str
    staged_at: str


class WindowsAuthenticodeVerifier:
    """Delegate to Windows WinVerifyTrust; unsupported platforms fail closed."""

    def __init__(self, *, verifier=None) -> None:
        self._verifier = verifier or WindowsMsixSignatureVerifier()

    def verify(self, installer_path: Path) -> bool:
        if not installer_path.is_file():
            return False
        try:
            return self._verifier.verify(installer_path) is True
        except (OSError, TypeError, ValueError):
            return False


class InstallerStager:
    """Download only backend-verified release assets into a bounded staging folder."""

    def __init__(self, *, http_get=None, signature_verifier=None, clock=None) -> None:
        self._http_get = http_get or requests.get
        self._signature_verifier = signature_verifier or WindowsAuthenticodeVerifier()
        self._clock = clock or (lambda: datetime.now(UTC).isoformat())

    def stage(self, candidate: InstallerCandidate, *, staging_root: Path) -> StagedInstaller:
        self._require_official_release_match(candidate)
        root = Path(staging_root)
        if not root.is_absolute() or root.is_symlink():
            raise InstallerStageError("staging directory must be an absolute, non-symlink path")
        try:
            root.mkdir(parents=True, exist_ok=True)
            if not root.is_dir() or root.is_symlink():
                raise InstallerStageError("staging directory is not a safe directory")
        except OSError:
            raise InstallerStageError("staging directory is unavailable") from None

        parsed_url = urlsplit(candidate.installer_url)
        suffix = Path(parsed_url.path).suffix.lower()
        if suffix not in ALLOWED_INSTALLER_SUFFIXES:
            raise InstallerStageError("installer file type is not supported")

        temp_path: Path | None = None
        response = None
        descriptor: int | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=".p6-604-download-",
                suffix=f".part{suffix}",
                dir=root,
            )
            temp_path = Path(temp_name)
            staged_file = os.fdopen(descriptor, "wb")
            descriptor = None
            digest = hashlib.sha256()
            total = 0
            declared_length: int | None = None
            with staged_file:
                response = self._http_get(
                    candidate.installer_url,
                    headers={
                        "Accept": "application/octet-stream",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=(3.05, 30),
                    allow_redirects=False,
                    stream=True,
                )
                if response.status_code != 200:
                    raise InstallerStageError("official installer source returned an unsuccessful response")

                headers = getattr(response, "headers", {})
                encoding = str(headers.get("Content-Encoding", "identity")).strip().lower()
                if encoding not in {"", "identity"}:
                    raise InstallerStageError("encoded installer responses are not accepted")
                content_length = headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except (TypeError, ValueError):
                        raise InstallerStageError("installer content length was invalid") from None
                    if declared_length < 1 or declared_length > MAX_INSTALLER_BYTES:
                        raise InstallerStageError("installer exceeded the staging size limit")

                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if not chunk:
                        continue
                    if not isinstance(chunk, bytes):
                        raise InstallerStageError("installer source returned non-binary content")
                    total += len(chunk)
                    if total > MAX_INSTALLER_BYTES:
                        raise InstallerStageError("installer exceeded the staging size limit")
                    digest.update(chunk)
                    staged_file.write(chunk)
                staged_file.flush()
                os.fsync(staged_file.fileno())

            actual_sha256 = digest.hexdigest()
            if total < 1 or (declared_length is not None and total != declared_length):
                raise InstallerStageError("installer size did not match its declared content length")
            if actual_sha256 != candidate.installer_sha256.lower():
                raise InstallerStageError("installer SHA-256 did not match the approved release digest")
            if actual_sha256 != candidate.official_asset_sha256:
                raise InstallerStageError("installer SHA-256 did not match the official release asset")

            if self._signature_verifier.verify(temp_path) is not True:
                raise InstallerStageError("Windows Authenticode trust validation failed")

            final_path = root / f"installer-{uuid.uuid4().hex}{suffix}"
            os.replace(temp_path, final_path)
            temp_path = None
            return StagedInstaller(
                package_id=candidate.package_id,
                version=candidate.version,
                architecture=candidate.architecture,
                file_path=str(final_path),
                file_size=total,
                sha256=actual_sha256,
                authenticode_valid=True,
                official_release_url=candidate.official_release_url or "",
                staged_at=self._clock(),
            )
        except InstallerStageError:
            raise
        except (OSError, requests.RequestException, TypeError, ValueError):
            raise InstallerStageError("installer could not be staged safely") from None
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _require_official_release_match(candidate: InstallerCandidate) -> None:
        if not isinstance(candidate, InstallerCandidate):
            raise InstallerStageError("installer candidate must come from the backend discovery service")
        if (
            candidate.publisher_verification != "VERIFIED"
            or candidate.official_version != candidate.version
            or not candidate.official_release_url
            or not candidate.official_asset_sha256
            or candidate.official_asset_sha256 != candidate.installer_sha256.lower()
        ):
            raise InstallerStageError("installer is not matched to a verified official release")
        parsed_url = urlsplit(candidate.installer_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.fragment
        ):
            raise InstallerStageError("installer URL is not an approved HTTPS URL")
