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
from contextlib import AbstractContextManager, ExitStack, contextmanager
from pathlib import Path
from typing import Protocol


class PlatformStorageUnavailable(RuntimeError):
    """The current platform has no reviewed secure-storage implementation."""


class DatabaseProtectionLease(Protocol):
    """Protection held for the complete lifetime of one SQLite connection."""

    def verify(self) -> None:
        """Verify the database and every present SQLite sidecar."""


class SecureStorageAdapter(Protocol):
    """OS-specific filesystem security contract for the SQLite database."""

    def protect_database(self, path: Path) -> AbstractContextManager[DatabaseProtectionLease]:
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



class WindowsSecureStorage:
    """Windows SQLite file verification under pinned, non-deletable directories.

    The directory DACL grants full access only to the current user and marks
    its ACE inheritable by files and subdirectories created by SQLite.
    """

    _READ_ATTRIBUTES = 0x80
    _READ_CONTROL = 0x20000
    _WRITE_DAC = 0x40000
    _SHARE_READ = 0x1
    _SHARE_WRITE = 0x2
    _SHARE_DELETE = 0x4
    _OPEN_EXISTING = 3
    _BACKUP_SEMANTICS = 0x02000000
    _OPEN_REPARSE_POINT = 0x00200000
    _DIRECTORY = 0x10
    _REPARSE = 0x400
    _ALL_ACCESS = 0x001F01FF
    _OI = 0x01
    _CI = 0x02
    _INHERITED = 0x10

    @staticmethod
    def _api():
        try:
            import ctypes
            import pywintypes
            import win32api
            import win32con
            import win32file
            import win32security
        except ImportError:
            raise PlatformStorageUnavailable("Windows security APIs are unavailable.") from None
        return ctypes, pywintypes, win32api, win32con, win32file, win32security

    @classmethod
    def _sid(cls):
        _ctypes, _pywintypes, api, con, _file, security = cls._api()
        token = security.OpenProcessToken(api.GetCurrentProcess(), con.TOKEN_QUERY)
        try:
            return security.GetTokenInformation(token, security.TokenUser)[0]
        finally:
            api.CloseHandle(token)

    @classmethod
    def _check_type(cls, handle, directory):
        ctypes, _pywintypes, _api, _con, file, _security = cls._api()
        attrs = file.GetFileInformationByHandle(handle)[0]
        if attrs & cls._REPARSE:
            class TagInfo(ctypes.Structure):
                _fields_ = [("attributes", ctypes.c_uint32), ("tag", ctypes.c_uint32)]
            info = TagInfo()
            kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
            fn = kernel.GetFileInformationByHandleEx
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
            fn.restype = ctypes.c_int
            if not fn(ctypes.c_void_p(int(handle)), 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise PlatformStorageUnavailable("Windows reparse tag could not be verified.")
            if info.tag in {0xA000000C, 0xA0000003}:
                raise PlatformStorageUnavailable(
                    "Windows path contains a redirection reparse point."
                )
        if bool(attrs & cls._DIRECTORY) != directory:
            raise PlatformStorageUnavailable("Windows SQLite path has an unsafe file type.")

    @classmethod
    def _verify_owner(cls, handle, sid):
        security = cls._api()[5]
        desc = security.GetSecurityInfo(
            handle, security.SE_FILE_OBJECT, security.OWNER_SECURITY_INFORMATION
        )
        if desc.GetSecurityDescriptorOwner() != sid:
            raise PlatformStorageUnavailable("Windows SQLite entry owner SID is not current user.")

    @classmethod
    def _secure_directory(cls, handle, sid):
        security = cls._api()[5]
        cls._verify_owner(handle, sid)
        acl = security.ACL()
        acl.AddAccessAllowedAceEx(security.ACL_REVISION, cls._OI | cls._CI, cls._ALL_ACCESS, sid)
        security.SetSecurityInfo(
            handle, security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None,
        )
        desc = security.GetSecurityInfo(
            handle, security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION,
        )
        dacl = desc.GetSecurityDescriptorDacl()
        if desc.GetSecurityDescriptorOwner() != sid or dacl is None or dacl.GetAceCount() != 1:
            raise PlatformStorageUnavailable("Windows SQLite directory DACL is not private.")
        header, mask, ace_sid = dacl.GetAce(0)
        if (header[0] != security.ACCESS_ALLOWED_ACE_TYPE or header[1] != cls._OI | cls._CI
                or mask != cls._ALL_ACCESS or ace_sid != sid):
            raise PlatformStorageUnavailable("Windows SQLite directory DACL inheritance is unsafe.")
        control, _revision = desc.GetSecurityDescriptorControl()
        if not control & security.SE_DACL_PROTECTED:
            raise PlatformStorageUnavailable("Windows SQLite directory DACL is not protected.")

    @contextmanager
    def protect_database(self, path: Path):
        if os.name != "nt" or not isinstance(path, Path) or not path.is_absolute():
            raise PlatformStorageUnavailable("Windows SQLite path is unavailable or not absolute.")
        if not path.drive or path.drive.startswith("\\\\"):
            raise PlatformStorageUnavailable("Windows SQLite path must be on a local drive.")
        _ctypes, pywintypes, _api, _con, file, _security = self._api()
        sid = self._sid()
        with ExitStack() as stack:
            components = [*reversed(path.parent.parents), path.parent]
            directory_handle = None
            for component in components:
                try:
                    handle = file.CreateFile(
                        str(component),
                        self._READ_ATTRIBUTES | self._READ_CONTROL | self._WRITE_DAC,
                        self._SHARE_READ | self._SHARE_WRITE, None, self._OPEN_EXISTING,
                        self._BACKUP_SEMANTICS | self._OPEN_REPARSE_POINT, None,
                    )
                except pywintypes.error:
                    raise PlatformStorageUnavailable(
                        "Windows SQLite directory could not be pinned."
                    ) from None
                stack.callback(file.CloseHandle, handle)
                self._check_type(handle, True)
                directory_handle = handle
            # Do not change an arbitrary ancestor: only secure the dedicated
            # database directory itself, which is pinned above.
            self._secure_directory(directory_handle, sid)
            lease = _WindowsDatabaseProtectionLease(path, sid)
            lease.verify()
            try:
                yield lease
            finally:
                lease.verify()


class _WindowsDatabaseProtectionLease:
    def __init__(self, path: Path, sid):
        self._path = path
        self._sid = sid

    def verify(self):
        adapter = WindowsSecureStorage
        _ctypes, pywintypes, _api, _con, file, security = adapter._api()
        for entry in (self._path, Path(f"{self._path}-wal"),
                      Path(f"{self._path}-shm"), Path(f"{self._path}-journal")):
            try:
                handle = file.CreateFile(
                    str(entry), adapter._READ_ATTRIBUTES | adapter._READ_CONTROL,
                    adapter._SHARE_READ | adapter._SHARE_WRITE | adapter._SHARE_DELETE,
                    None, adapter._OPEN_EXISTING, adapter._OPEN_REPARSE_POINT, None,
                )
            except pywintypes.error as exc:
                code = getattr(exc, "winerror", None)
                if code is None and getattr(exc, "args", None):
                    code = exc.args[0]
                if code in (2, 3):
                    continue
                raise PlatformStorageUnavailable(
                    "SQLite sidecar security could not be checked."
                ) from None
            try:
                adapter._check_type(handle, False)
                adapter._verify_owner(handle, self._sid)
                desc = security.GetSecurityInfo(
                    handle, security.SE_FILE_OBJECT, security.DACL_SECURITY_INFORMATION
                )
                dacl = desc.GetSecurityDescriptorDacl()
                if dacl is None or dacl.GetAceCount() != 1:
                    raise PlatformStorageUnavailable(
                        "SQLite database or sidecar DACL is not private."
                    )
                header, mask, ace_sid = dacl.GetAce(0)
                if (header[0] != security.ACCESS_ALLOWED_ACE_TYPE
                        or not header[1] & adapter._INHERITED
                        or mask != adapter._ALL_ACCESS or ace_sid != self._sid):
                    raise PlatformStorageUnavailable(
                        "SQLite database or sidecar DACL is not inherited safely."
                    )
            finally:
                file.CloseHandle(handle)


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
            "Windows job-store storage remains disabled until the native adapter "
            "passes dedicated Windows integration tests and independent security review."
        )
    if current == "darwin":
        raise PlatformStorageUnavailable(
            "macOS job-store storage is disabled pending native ACL and "
            "handle-based path-race protections."
        )
    raise PlatformStorageUnavailable(
        f"Job-store storage is not supported on platform {current!r}."
    )
