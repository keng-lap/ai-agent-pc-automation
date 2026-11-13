"""Platform-specific protection for the local SQLite job database.

The Job Store depends on this narrow interface instead of embedding OS checks.
Only Linux is enabled initially. Windows and macOS remain fail-closed until
native ACL/owner/reparse-point (Windows) or ACL/path-race (macOS) controls are
implemented and independently reviewed.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from typing import Protocol


class PlatformStorageUnavailable(RuntimeError):
    """The current platform has no reviewed secure-storage implementation."""


class SecureStorageAdapter(Protocol):
    """OS-specific filesystem security contract for the SQLite database."""

    def prepare_database_path(self, path: Path) -> None:
        """Validate and prepare the private parent and existing database path."""

    def finalize_database_file(self, path: Path) -> None:
        """Apply/verify the database file's final access controls."""


class LinuxSecureStorage:
    """Linux private-directory/file-mode implementation."""

    def prepare_database_path(self, path: Path) -> None:
        try:
            for part in (path.parent, *path.parent.parents):
                if part.exists() and stat.S_ISLNK(part.lstat().st_mode):
                    raise PlatformStorageUnavailable(
                        "Job-store path contains a symbolic link."
                    )
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            parent_mode = stat.S_IMODE(path.parent.stat().st_mode)
            if parent_mode & 0o077:
                raise PlatformStorageUnavailable(
                    "Job-store directory permissions are too broad."
                )
            if path.exists():
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise PlatformStorageUnavailable(
                        "Job-store database is not a regular file."
                    )
                if stat.S_IMODE(info.st_mode) & 0o077:
                    raise PlatformStorageUnavailable(
                        "Job-store database permissions are too broad."
                    )
            path.parent.chmod(0o700)
        except PlatformStorageUnavailable:
            raise
        except OSError:
            raise PlatformStorageUnavailable(
                "Job-store path could not be secured."
            ) from None

    def finalize_database_file(self, path: Path) -> None:
        try:
            path.chmod(0o600)
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise PlatformStorageUnavailable(
                    "Job-store database changed to an unsafe file type."
                )
            if stat.S_IMODE(info.st_mode) & 0o077:
                raise PlatformStorageUnavailable(
                    "Job-store database permissions are too broad."
                )
        except PlatformStorageUnavailable:
            raise
        except OSError:
            raise PlatformStorageUnavailable(
                "Job-store database permissions could not be secured."
            ) from None


def create_platform_secure_storage(
    *, platform: str | None = None
) -> SecureStorageAdapter:
    """Return the reviewed adapter for the requested/current OS.

    The platform argument exists to make platform selection testable; production
    callers must omit it so the runtime platform determines the implementation.
    """
    current = platform or sys.platform
    if current.startswith("linux"):
        return LinuxSecureStorage()
    if current == "win32":
        raise PlatformStorageUnavailable(
            "Windows job-store storage is disabled pending native DACL, owner "
            "SID, reparse-point, and handle-based path-race protections."
        )
    if current == "darwin":
        raise PlatformStorageUnavailable(
            "macOS job-store storage is disabled pending native ACL and "
            "handle-based path-race protections."
        )
    raise PlatformStorageUnavailable(
        f"Job-store storage is not supported on platform {current!r}."
    )
