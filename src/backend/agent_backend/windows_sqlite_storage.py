"""Windows ACL protection for SQLite databases and their sidecar files.

The adapter protects the database directory with a current-user-only,
protected DACL whose inheritable ACE secures SQLite-created files (database,
WAL, SHM and rollback journals) at creation time. It keeps verified ancestor
and directory handles open without FILE_SHARE_DELETE for its lifetime, so
another Windows identity cannot replace the directory during SQLite use.

This does not defend against another process running as the same Windows user.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path

from .platform_storage import PlatformStorageUnavailable
from .windows_secret_storage import WindowsSecretFile

_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_GENERIC_READ = 0x80000000
_READ_CONTROL = 0x00020000
_WRITE_DAC = 0x00040000
_OPEN_EXISTING = 3
_FILE_ALL_ACCESS = 0x001F01FF
_SQLITE_SUFFIXES = ("", "-wal", "-shm", "-journal")


class WindowsSQLiteStorageError(PlatformStorageUnavailable):
    """Windows SQLite storage could not be proven private and stable."""


class WindowsSQLiteStorage:
    """Protect a SQLite database directory and all SQLite sidecar files."""

    def __init__(self, path: Path) -> None:
        if os.name != "nt":
            raise WindowsSQLiteStorageError("Windows SQLite storage is unavailable.")
        if not isinstance(path, Path) or not path.is_absolute():
            raise WindowsSQLiteStorageError("SQLite database path must be absolute.")
        self.path = Path(os.path.abspath(path))
        self._stack: ExitStack | None = None
        self._directory_handle = None
        self._sid = None
        self._initially_missing: set[str] = set()

    @staticmethod
    def _api():
        try:
            import pywintypes
            import win32file
            import win32security
        except ImportError:
            raise WindowsSQLiteStorageError(
                "Windows security APIs are unavailable."
            ) from None
        return pywintypes, win32file, win32security

    def _set_inheritable_directory_dacl(self, handle, sid) -> None:
        _pywintypes, _win32file, security = self._api()
        descriptor = security.GetSecurityInfo(
            handle,
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != sid:
            raise WindowsSQLiteStorageError(
                "SQLite directory owner SID is not the current user."
            )

        acl = security.ACL()
        inherit_flags = (
            security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE
        )
        acl.AddAccessAllowedAceEx(
            security.ACL_REVISION,
            inherit_flags,
            _FILE_ALL_ACCESS,
            sid,
        )
        security.SetSecurityInfo(
            handle,
            security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION
            | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        self._verify_directory_dacl(handle, sid)

    @classmethod
    def _verify_directory_dacl(cls, handle, sid) -> None:
        _pywintypes, _win32file, security = cls._api()
        descriptor = security.GetSecurityInfo(
            handle,
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION
            | security.DACL_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != sid:
            raise WindowsSQLiteStorageError(
                "SQLite directory owner SID is not the current user."
            )
        dacl = descriptor.GetSecurityDescriptorDacl()
        if dacl is None or dacl.GetAceCount() != 1:
            raise WindowsSQLiteStorageError(
                "SQLite directory DACL is not owner-only."
            )
        header, mask, ace_sid = dacl.GetAce(0)
        expected_flags = (
            security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE
        )
        if (
            header[0] != security.ACCESS_ALLOWED_ACE_TYPE
            or header[1] != expected_flags
            or mask != _FILE_ALL_ACCESS
            or ace_sid != sid
        ):
            raise WindowsSQLiteStorageError(
                "SQLite directory DACL inheritance is not owner-only."
            )
        control, _revision = descriptor.GetSecurityDescriptorControl()
        if not control & security.SE_DACL_PROTECTED:
            raise WindowsSQLiteStorageError(
                "SQLite directory DACL inheritance is not protected."
            )

    @classmethod
    def _secure_existing_file(
        cls, path: Path, sid, *, allow_owner_change: bool = False
    ) -> bool:
        pywintypes, win32file, security = cls._api()
        try:
            handle = win32file.CreateFile(
                str(path),
                _GENERIC_READ
                | _READ_CONTROL
                | _WRITE_DAC
                | (_WRITE_OWNER if allow_owner_change else 0),
                _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                None,
                _OPEN_EXISTING,
                _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        except pywintypes.error as exc:
            error_code = getattr(exc, "winerror", None)
            if error_code is None and getattr(exc, "args", None):
                error_code = exc.args[0]
            if error_code in (2, 3):
                return False
            raise WindowsSQLiteStorageError(
                f"SQLite file could not be opened safely (Win32 error {error_code})."
            ) from None

        try:
            attributes = win32file.GetFileInformationByHandle(handle)[0]
            if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise WindowsSQLiteStorageError(
                    "SQLite database or sidecar is a reparse point."
                )
            if attributes & _FILE_ATTRIBUTE_DIRECTORY:
                raise WindowsSQLiteStorageError(
                    "SQLite database or sidecar is not a regular file."
                )
            descriptor = security.GetSecurityInfo(
                handle,
                security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION,
            )
            owner = descriptor.GetSecurityDescriptorOwner()
            if owner != sid:
                if not allow_owner_change:
                    raise WindowsSQLiteStorageError(
                        "SQLite file owner SID is not the current user."
                    )
                security.SetSecurityInfo(
                    handle,
                    security.SE_FILE_OBJECT,
                    security.OWNER_SECURITY_INFORMATION,
                    sid,
                    None,
                    None,
                    None,
                )

            acl = security.ACL()
            acl.AddAccessAllowedAceEx(
                security.ACL_REVISION,
                0,
                _FILE_ALL_ACCESS,
                sid,
            )
            security.SetSecurityInfo(
                handle,
                security.SE_FILE_OBJECT,
                security.DACL_SECURITY_INFORMATION
                | security.PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                acl,
                None,
            )
            cls._verify_file_dacl(handle, sid)
            return True
        finally:
            win32file.CloseHandle(handle)

    @classmethod
    def _verify_inherited_file_dacl(cls, path: Path, sid) -> None:
        pywintypes, win32file, security = cls._api()
        try:
            handle = win32file.CreateFile(
                str(path),
                _GENERIC_READ | _READ_CONTROL,
                _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                None,
                _OPEN_EXISTING,
                _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        except pywintypes.error:
            raise WindowsSQLiteStorageError(
                "New SQLite file could not be opened to verify inherited ACL."
            ) from None
        try:
            attributes = win32file.GetFileInformationByHandle(handle)[0]
            if attributes & (_FILE_ATTRIBUTE_REPARSE_POINT | _FILE_ATTRIBUTE_DIRECTORY):
                raise WindowsSQLiteStorageError(
                    "New SQLite file has an unsafe file attribute."
                )
            descriptor = security.GetSecurityInfo(
                handle,
                security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION
                | security.DACL_SECURITY_INFORMATION,
            )
            # SQLite may create files with the process token's default
            # owner (for example, BUILTIN\\Administrators on an elevated
            # runner). The inherited DACL, not this owner field, must protect
            # the file from other identities until finalize repairs ownership.
            dacl = descriptor.GetSecurityDescriptorDacl()
            if dacl is None or dacl.GetAceCount() != 1:
                raise WindowsSQLiteStorageError(
                    "New SQLite file did not inherit an owner-only DACL."
                )
            header, mask, ace_sid = dacl.GetAce(0)
            if (
                header[0] != security.ACCESS_ALLOWED_ACE_TYPE
                or header[1] != security.INHERITED_ACE
                or mask != _FILE_ALL_ACCESS
                or ace_sid != sid
            ):
                raise WindowsSQLiteStorageError(
                    "New SQLite file inherited an unexpected DACL."
                )
            control, _revision = descriptor.GetSecurityDescriptorControl()
            if control & security.SE_DACL_PROTECTED:
                raise WindowsSQLiteStorageError(
                    "New SQLite file did not inherit its directory DACL."
                )
        finally:
            win32file.CloseHandle(handle)

    @classmethod
    def _verify_file_dacl(cls, handle, sid) -> None:
        _pywintypes, _win32file, security = cls._api()
        descriptor = security.GetSecurityInfo(
            handle,
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION
            | security.DACL_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != sid:
            raise WindowsSQLiteStorageError(
                "SQLite file owner SID is not the current user."
            )
        dacl = descriptor.GetSecurityDescriptorDacl()
        if dacl is None or dacl.GetAceCount() != 1:
            raise WindowsSQLiteStorageError("SQLite file DACL is not owner-only.")
        header, mask, ace_sid = dacl.GetAce(0)
        if (
            header[0] != security.ACCESS_ALLOWED_ACE_TYPE
            or header[1] != 0
            or mask != _FILE_ALL_ACCESS
            or ace_sid != sid
        ):
            raise WindowsSQLiteStorageError("SQLite file DACL is not owner-only.")
        control, _revision = descriptor.GetSecurityDescriptorControl()
        if not control & security.SE_DACL_PROTECTED:
            raise WindowsSQLiteStorageError(
                "SQLite file DACL inheritance is not disabled."
            )

    def prepare_database_path(self, path: Path) -> None:
        if Path(os.path.abspath(path)) != self.path:
            raise WindowsSQLiteStorageError("SQLite path differs from prepared path.")
        if self._stack is not None:
            return

        stack = ExitStack()
        try:
            secret_path = WindowsSecretFile(self.path)
            directory_handle, sid = secret_path._parent_handles(stack)
            # The final directory handle and every ancestor handle remain open
            # without FILE_SHARE_DELETE while SQLite uses pathname-based I/O.
            self._set_inheritable_directory_dacl(directory_handle, sid)
            self._directory_handle = directory_handle
            self._sid = sid
            self._stack = stack
            for suffix in _SQLITE_SUFFIXES:
                if not self._secure_existing_file(
                    Path(str(self.path) + suffix),
                    sid,
                ):
                    self._initially_missing.add(suffix)
        except Exception as exc:
            stack.close()
            self._stack = None
            self._directory_handle = None
            self._sid = None
            if isinstance(exc, WindowsSQLiteStorageError):
                raise
            raise WindowsSQLiteStorageError(
                "SQLite database directory could not be secured."
            ) from None

    def finalize_database_file(self, path: Path) -> None:
        if self._stack is None or self._sid is None:
            raise WindowsSQLiteStorageError(
                "SQLite directory protection was not prepared."
            )
        if Path(os.path.abspath(path)) != self.path:
            raise WindowsSQLiteStorageError("SQLite path differs from prepared path.")
        self._verify_directory_dacl(self._directory_handle, self._sid)
        for suffix in _SQLITE_SUFFIXES:
            self._secure_existing_file(
                Path(str(self.path) + suffix),
                self._sid,
                allow_owner_change=suffix in self._initially_missing,
            )

    def close(self) -> None:
        """Release pinned directory handles after every SQLite connection closes."""
        if self._stack is not None:
            self._stack.close()
        self._stack = None
        self._directory_handle = None
        self._sid = None
        self._initially_missing.clear()

    def __enter__(self) -> WindowsSQLiteStorage:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
