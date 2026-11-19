"""Platform-specific protection for the local SQLite job database.

The Job Store depends on this narrow interface instead of embedding OS checks.
Linux is currently the only enabled adapter. Windows remains fail-closed until
native DACL, owner SID, reparse-point and handle-based path-race protections
are implemented and independently reviewed. macOS remains unsupported.
"""

from __future__ import annotations

import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Protocol


class PlatformStorageUnavailable(RuntimeError):
    """The current platform has no reviewed secure-storage implementation."""


class DatabaseProtectionLease(Protocol):
    """Protection held for the complete lifetime of one SQLite connection."""

    def verify(self) -> None:
        """Verify the database and every present SQLite sidecar."""


class SecureStorageAdapter(Protocol):
    """OS-specific filesystem security contract for the SQLite database."""

    def protect_database(self, path: Path) -> ContextManager[DatabaseProtectionLease]:
        """Hold path protection until the caller closes its SQLite connection."""


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

            # Inspect the database entry before validating directory modes.
            # lstat() does not follow a database symlink.
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise PlatformStorageUnavailable(
                        "Job-store database path contains a symbolic link."
                    )
                if not stat.S_ISREG(info.st_mode):
                    raise PlatformStorageUnavailable(
                        "Job-store database is not a regular file."
                    )
                if info.st_uid != os.geteuid():
                    raise PlatformStorageUnavailable(
                        "Job-store database is not owned by the current user."
                    )
                if stat.S_IMODE(info.st_mode) & 0o077:
                    raise PlatformStorageUnavailable(
                        "Job-store database permissions are too broad."
                    )

            parent_info = path.parent.stat()
            if parent_info.st_uid != os.geteuid():
                raise PlatformStorageUnavailable(
                    "Job-store directory is not owned by the current user."
                )
            parent_mode = stat.S_IMODE(parent_info.st_mode)
            if parent_mode & 0o077:
                raise PlatformStorageUnavailable(
                    "Job-store directory permissions are too broad."
                )
            path.parent.chmod(0o700)
        except PlatformStorageUnavailable:
            raise
        except OSError:
            raise PlatformStorageUnavailable(
                "Job-store path could not be secured."
            ) from None

    @contextmanager
    def protect_database(self, path: Path):
        self.prepare_database_path(path)
        lease = _LinuxDatabaseProtectionLease(path)
        try:
            yield lease
        finally:
            # The caller closes SQLite before this context exits. Verify once
            # more at lease release so sidecars created during the connection
            # lifetime cannot escape the private-file checks.
            lease.verify()


class _LinuxDatabaseProtectionLease:
    """Re-verify SQLite's complete file set while the parent remains private."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def verify(self) -> None:
        try:
            for candidate in (
                self._path,
                Path(f"{self._path}-wal"),
                Path(f"{self._path}-shm"),
                Path(f"{self._path}-journal"),
            ):
                if not candidate.exists() and not candidate.is_symlink():
                    continue
                info = candidate.lstat()
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    raise PlatformStorageUnavailable(
                        "Job-store database or sidecar is not a regular file."
                    )
                if info.st_uid != os.geteuid():
                    raise PlatformStorageUnavailable(
                        "Job-store database or sidecar is not owned by the current user."
                    )
                candidate.chmod(0o600)
                verified = candidate.lstat()
                if stat.S_IMODE(verified.st_mode) & 0o077:
                    raise PlatformStorageUnavailable(
                        "Job-store database or sidecar permissions are too broad."
                    )
        except PlatformStorageUnavailable:
            raise
        except OSError:
            raise PlatformStorageUnavailable(
                "Job-store database or sidecar permissions could not be secured."
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
