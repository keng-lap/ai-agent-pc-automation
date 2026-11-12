"""Exact-artifact WinGet local-manifest adapter foundation (P6-603).

The generated manifest pins the approved installer URL and SHA-256. It is
prepared from an immutable InstallApprovalBinding, never from model text.
This module deliberately does not execute WinGet or an installer yet.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent_backend.software_approval import InstallApprovalBinding

MANIFEST_VERSION = "1.10.0"
SUPPORTED_INSTALLER_TYPES = frozenset({"exe", "msi", "msix", "appx"})
INSTALLER_SUFFIXES = {
    "exe": ".exe",
    "msi": ".msi",
    "msix": ".msix",
    "appx": ".appx",
}
_PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}$")


class WinGetAdapterError(RuntimeError):
    """A local manifest could not be prepared safely."""


class PreparedWinGetInstall(BaseModel):
    """Opaque result of preparing the exact approved package manifest."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    manifest_directory: str = Field(min_length=1, max_length=2048)
    manifest_file_names: tuple[str, str, str]
    package_id: str
    version: str
    installer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_local_manifest_documents(
    binding: InstallApprovalBinding,
) -> dict[str, str]:
    """Build a minimal three-file manifest from the exact approved evidence."""
    if not isinstance(binding, InstallApprovalBinding):
        raise TypeError("an immutable install approval binding is required")

    evidence = binding.evidence
    if (
        not _PACKAGE_ID.fullmatch(evidence.package_id)
        or not _VERSION.fullmatch(evidence.version)
        or evidence.installer_type not in SUPPORTED_INSTALLER_TYPES
        or evidence.scope != "user"
        or evidence.source != "winget"
    ):
        raise WinGetAdapterError("approved package is outside the supported WinGet adapter contract")

    parsed_url = urlsplit(evidence.installer_url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
        or Path(parsed_url.path).suffix.lower() != INSTALLER_SUFFIXES[evidence.installer_type]
    ):
        raise WinGetAdapterError("approved installer URL does not match its verified installer type")

    common = {
        "ManifestVersion": MANIFEST_VERSION,
        "PackageIdentifier": evidence.package_id,
        "PackageVersion": evidence.version,
    }
    version_doc = {
        **common,
        "DefaultLocale": "en-US",
        "ManifestType": "version",
    }
    locale_doc = {
        **common,
        "PackageLocale": "en-US",
        "Publisher": evidence.publisher,
        "PackageName": evidence.package_name,
        "ManifestType": "defaultLocale",
    }
    installer_doc = {
        **common,
        "ManifestType": "installer",
        "InstallerType": evidence.installer_type,
        "Installers": [
            {
                "Architecture": evidence.architecture,
                "Scope": "user",
                "InstallerUrl": evidence.installer_url,
                "InstallerSha256": evidence.installer_sha256,
            }
        ],
    }

    documents = {
        f"{evidence.package_id}.yaml": version_doc,
        f"{evidence.package_id}.locale.en-US.yaml": locale_doc,
        f"{evidence.package_id}.installer.yaml": installer_doc,
    }
    return {
        name: yaml.safe_dump(
            document,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
        for name, document in documents.items()
    }


def build_install_arguments(
    binding: InstallApprovalBinding,
    prepared: PreparedWinGetInstall,
    *,
    work_root: Path,
) -> tuple[str, ...]:
    """Build argv only for the prepared directory bound to this exact approval."""
    if not isinstance(binding, InstallApprovalBinding):
        raise TypeError("an immutable install approval binding is required")
    if not isinstance(prepared, PreparedWinGetInstall):
        raise TypeError("a prepared WinGet install is required")
    root = Path(work_root)
    manifest_directory = Path(prepared.manifest_directory)
    expected_documents = build_local_manifest_documents(binding)
    if (
        prepared.approval_digest != binding.approval_digest
        or prepared.package_id != binding.evidence.package_id
        or prepared.version != binding.evidence.version
        or prepared.installer_sha256 != binding.evidence.installer_sha256
        or set(prepared.manifest_file_names) != set(expected_documents)
    ):
        raise WinGetAdapterError("prepared manifest does not match the exact approval binding")
    if not root.is_absolute() or root.is_symlink():
        raise WinGetAdapterError("work root must be an absolute non-symlink directory")
    try:
        if not root.is_dir() or root.resolve(strict=True) != root:
            raise WinGetAdapterError("work root is unavailable or unsafe")
        binding.ensure_fresh(now=datetime.now(UTC))
    except (TypeError, ValueError):
        raise WinGetAdapterError("approval evidence is expired or invalid") from None
    try:
        root_real = root.resolve(strict=True)
        if (
            not manifest_directory.is_dir()
            or manifest_directory.is_symlink()
            or manifest_directory.resolve(strict=True) != manifest_directory
            or manifest_directory.parent != root_real
            or not manifest_directory.name.startswith("p6-603-")
        ):
            raise WinGetAdapterError("manifest directory is unavailable or outside the fixed work root")
        actual_names = {entry.name for entry in manifest_directory.iterdir()}
        if actual_names != set(expected_documents):
            raise WinGetAdapterError("manifest file set does not match the approved package")
        for file_name, expected_content in expected_documents.items():
            target = manifest_directory / file_name
            if target.is_symlink() or not target.is_file():
                raise WinGetAdapterError("manifest file is unavailable or unsafe")
            if target.read_text(encoding="utf-8") != expected_content:
                raise WinGetAdapterError("manifest content no longer matches the approved evidence")
    except OSError:
        raise WinGetAdapterError("manifest directory could not be verified") from None
    return (
        "install",
        "--manifest",
        str(manifest_directory),
        "--scope",
        "user",
        "--architecture",
        binding.evidence.architecture,
        "--silent",
        "--disable-interactivity",
        "--skip-dependencies",
        "--no-upgrade",
    )


def prepare_approved_install(
    binding: InstallApprovalBinding,
    *,
    work_root: Path,
    now: datetime | None = None,
) -> PreparedWinGetInstall:
    """Write a private, short-lived local manifest directory for a fresh approval."""
    if not isinstance(binding, InstallApprovalBinding):
        raise TypeError("an immutable install approval binding is required")
    current_time = now or datetime.now(UTC)
    try:
        binding.ensure_fresh(now=current_time)
    except (TypeError, ValueError):
        raise WinGetAdapterError("approval evidence is expired or invalid") from None

    root = Path(work_root)
    if not root.is_absolute() or root.is_symlink():
        raise WinGetAdapterError("work root must be an absolute non-symlink directory")
    try:
        parent = root.parent
        if (
            not parent.is_dir()
            or parent.is_symlink()
            or parent.resolve(strict=True) != parent
        ):
            raise WinGetAdapterError("work root parent must already exist and be a real directory")
        if root.exists():
            if not root.is_dir() or root.resolve(strict=True) != root:
                raise WinGetAdapterError("work root is unavailable or unsafe")
        else:
            root.mkdir(mode=0o700)
        root_real = root.resolve(strict=True)
        if root_real != root:
            raise WinGetAdapterError("work root must not resolve through a link or reparse path")
    except OSError:
        raise WinGetAdapterError("work root is unavailable") from None

    documents = build_local_manifest_documents(binding)
    directory = Path(tempfile.mkdtemp(prefix="p6-603-", dir=root))
    try:
        for file_name, content in documents.items():
            if Path(file_name).name != file_name:
                raise WinGetAdapterError("generated manifest file name was invalid")
            target = directory / file_name
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())

        names = tuple(sorted(documents))
        return PreparedWinGetInstall(
            manifest_directory=str(directory),
            manifest_file_names=names,
            package_id=binding.evidence.package_id,
            version=binding.evidence.version,
            installer_sha256=binding.evidence.installer_sha256,
            approval_digest=binding.approval_digest,
        )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def cleanup_prepared_install(prepared: PreparedWinGetInstall, *, work_root: Path) -> None:
    """Remove only a generated manifest directory directly under the fixed work root."""
    if not isinstance(prepared, PreparedWinGetInstall):
        raise TypeError("a prepared WinGet install is required")
    root = Path(work_root)
    directory = Path(prepared.manifest_directory)
    try:
        if not root.is_dir() or root.is_symlink() or root.resolve(strict=True) != root:
            raise WinGetAdapterError("refusing to clean through an unsafe work root")
        root_real = root.resolve(strict=True)
        directory_real = directory.resolve(strict=True)
        if directory_real.parent != root_real or not directory_real.name.startswith("p6-603-"):
            raise WinGetAdapterError("refusing to clean a path outside the adapter work root")
        if directory.is_symlink():
            raise WinGetAdapterError("refusing to clean a linked manifest directory")
        shutil.rmtree(directory_real)
    except FileNotFoundError:
        return
    except OSError:
        raise WinGetAdapterError("prepared manifest cleanup failed") from None



@contextmanager
def lock_prepared_manifest(
    binding: InstallApprovalBinding,
    prepared: PreparedWinGetInstall,
    *,
    work_root: Path,
) -> Iterator[tuple[str, ...]]:
    """Lock the manifest directory/files against write/delete through WinGet's read.

    Windows sharing semantics are used deliberately: existing handles allow
    FILE_SHARE_READ only, so another process cannot replace or modify a manifest
    while the caller runs WinGet inside this context. The exact manifest is
    revalidated after all locks are held.
    """
    if os.name != "nt":
        raise WinGetAdapterError("manifest locking requires Windows")
    arguments = build_install_arguments(binding, prepared, work_root=work_root)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    generic_read = 0x80000000
    file_read_attributes = 0x00000080
    share_read_only = 0x00000001
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    invalid_handle = ctypes.c_void_p(-1).value
    manifest_directory = Path(prepared.manifest_directory)
    handles: list[ctypes.c_void_p] = []

    def open_locked(path: Path, *, is_directory: bool = False) -> None:
        access = file_read_attributes if is_directory else generic_read
        flags = file_flag_backup_semantics if is_directory else 0x00000080
        handle = create_file(
            str(path),
            access,
            share_read_only,
            None,
            open_existing,
            flags,
            None,
        )
        if handle in (None, invalid_handle):
            raise WinGetAdapterError("could not lock the approved manifest against modification")
        handles.append(handle)

    try:
        # Lock the directory first, then each known manifest file.
        open_locked(manifest_directory, is_directory=True)
        expected_documents = build_local_manifest_documents(binding)
        for file_name in sorted(expected_documents):
            open_locked(manifest_directory / file_name)

        # Close the validation-to-lock race: verify exact bytes again while
        # write/delete sharing is denied for the directory and all manifest files.
        arguments = build_install_arguments(binding, prepared, work_root=work_root)
        yield arguments
    except OSError:
        raise WinGetAdapterError("approved manifest could not be locked safely") from None
    finally:
        for handle in reversed(handles):
            close_handle(handle)
