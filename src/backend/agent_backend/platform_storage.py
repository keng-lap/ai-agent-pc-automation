"""Platform-specific protection for the local SQLite job database.

The Job Store depends on this narrow interface instead of embedding OS checks.
Linux and Windows have dedicated platform adapters. The Windows adapter is
covered by native ACL, owner SID, reparse-point, SQLite sidecar and mutex tests
in the Windows CI workflow. macOS remains unsupported.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
from contextlib import AbstractContextManager, ExitStack, contextmanager
from pathlib import Path
from typing import ClassVar, Protocol


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
        # Reject an unsafe pre-existing sidecar before SQLite can open the
        # database or follow any of its sidecar names.
        lease.verify()
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
                path_only = getattr(os, "O_PATH", None)
                if path_only is None:
                    raise PlatformStorageUnavailable(
                        "Lock-safe Linux file verification is unavailable."
                    )
                flags = path_only | getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                try:
                    # O_PATH pins the entry without opening a regular file
                    # description that could release this process's POSIX
                    # locks on SQLite's database or -shm inode when closed.
                    descriptor = os.open(candidate, flags)
                except FileNotFoundError:
                    # SQLite may remove a WAL/SHM/journal between checks.
                    # Absence at the atomic open point is a normal state.
                    continue
                try:
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode):
                        raise PlatformStorageUnavailable(
                            "Job-store database or sidecar is not a regular file."
                        )
                    if info.st_uid != os.geteuid():
                        raise PlatformStorageUnavailable(
                            "Job-store database or sidecar is not owned by the current user."
                        )
                    if stat.S_IMODE(info.st_mode) & 0o077:
                        # chmod through the procfs fd link targets this exact
                        # pinned inode; no ordinary descriptor is opened.
                        os.chmod(f"/proc/self/fd/{descriptor}", 0o600)
                    verified = os.fstat(descriptor)
                    if stat.S_IMODE(verified.st_mode) & 0o077:
                        raise PlatformStorageUnavailable(
                            "Job-store database or sidecar permissions are too broad."
                        )
                finally:
                    os.close(descriptor)
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
    _FILE_OPEN_REPARSE_POINT = _OPEN_REPARSE_POINT
    _DIRECTORY = 0x10
    _REPARSE = 0x400
    _ALL_ACCESS = 0x001F01FF
    _FILE_ADD_SUBDIRECTORY = 0x0004
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_CREATE = 2
    _FILE_OPEN = 1
    _FILE_DIRECTORY_FILE = 0x00000001
    _FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
    _OBJ_CASE_INSENSITIVE = 0x00000040
    _STATUS_OBJECT_NAME_COLLISION = 0xC0000035
    _OI = 0x01
    _CI = 0x02

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
        _ctypes, _pywintypes, _api, _con, file, _security = cls._api()
        attrs = file.GetFileInformationByHandle(handle)[0]
        if attrs & cls._REPARSE:
            # This adapter has no reviewed allow-list of reparse providers.
            # Reject every reparse point rather than trying to classify tags.
            raise PlatformStorageUnavailable(
                "Windows path contains an unsupported reparse point."
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

    @staticmethod
    def _read_conventional_allow_ace(dacl):
        """Reject ACE formats pywin32 cannot represent as a conventional tuple."""
        try:
            ace = dacl.GetAce(0)
            if (
                not isinstance(ace, tuple)
                or len(ace) != 3
                or not isinstance(ace[0], tuple)
                or len(ace[0]) != 2
            ):
                raise PlatformStorageUnavailable(
                    "Windows SQLite security descriptor uses an unsupported ACE format."
                )
            return ace
        except PlatformStorageUnavailable:
            raise
        except (NotImplementedError, TypeError, ValueError, IndexError):
            raise PlatformStorageUnavailable(
                "Windows SQLite security descriptor uses an unsupported ACE format."
            ) from None

    @classmethod
    def _verify_directory(cls, handle, sid):
        """Accept only an already-private, protected application state directory.

        Existing ACLs are never rewritten: an unexpected descriptor is a
        hard failure, not an invitation to change permissions on a caller path.
        """
        security = cls._api()[5]
        desc = security.GetSecurityInfo(
            handle, security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION,
        )
        if desc.GetSecurityDescriptorOwner() != sid:
            raise PlatformStorageUnavailable(
                "Windows SQLite state directory owner SID is not current user."
            )
        dacl = desc.GetSecurityDescriptorDacl()
        if dacl is None or dacl.GetAceCount() != 1:
            raise PlatformStorageUnavailable(
                "Windows SQLite state directory DACL is not private."
            )
        header, mask, ace_sid = cls._read_conventional_allow_ace(dacl)
        if (
            header[0] != security.ACCESS_ALLOWED_ACE_TYPE
            or header[1] != (cls._OI | cls._CI)
            or mask != cls._ALL_ACCESS
            or ace_sid != sid
        ):
            raise PlatformStorageUnavailable(
                "Windows SQLite state directory DACL is not the required owner-only ACL."
            )
        control, _revision = desc.GetSecurityDescriptorControl()
        if not control & security.SE_DACL_PROTECTED:
            raise PlatformStorageUnavailable(
                "Windows SQLite state directory DACL is not protected."
            )

    @classmethod
    def _create_or_open_private_directory(cls, parent_handle, name: str, sid):
        """Create/open the exact child relative to a pinned parent handle.

        NtCreateFile returns the handle to the object created/opened in the
        same operation. This avoids the CreateDirectoryW-then-open-by-path
        namespace gap in which a child entry could otherwise be substituted.
        """
        ctypes, pywintypes, _api, _con, _file, security = cls._api()
        ntdll = ctypes.WinDLL("ntdll.dll")
        advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)

        class UnicodeString(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("Length", ctypes.c_ushort),
                ("MaximumLength", ctypes.c_ushort),
                ("Buffer", ctypes.c_wchar_p),
            ]

        class ObjectAttributes(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("Length", ctypes.c_ulong),
                ("RootDirectory", ctypes.c_void_p),
                ("ObjectName", ctypes.POINTER(UnicodeString)),
                ("Attributes", ctypes.c_ulong),
                ("SecurityDescriptor", ctypes.c_void_p),
                ("SecurityQualityOfService", ctypes.c_void_p),
            ]

        class IoStatusBlock(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("Status", ctypes.c_void_p),
                ("Information", ctypes.c_size_t),
            ]

        sid_text = security.ConvertSidToStringSid(sid)
        sddl = f"O:{sid_text}D:P(A;OICI;0x001F01FF;;;{sid_text})"
        descriptor = ctypes.c_void_p()
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32),
        ]
        convert.restype = ctypes.c_int
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise PlatformStorageUnavailable(
                "Secure Windows SQLite directory security descriptor could not be created."
            )

        name_buffer = ctypes.create_unicode_buffer(name)
        object_name = UnicodeString(
            len(name.encode("utf-16-le")),
            len(name.encode("utf-16-le")) + 2,
            ctypes.cast(name_buffer, ctypes.c_wchar_p),
        )
        attributes = ObjectAttributes(
            ctypes.sizeof(ObjectAttributes),
            int(parent_handle),
            ctypes.pointer(object_name),
            cls._OBJ_CASE_INSENSITIVE,
            descriptor,
            None,
        )
        io_status = IoStatusBlock()
        result_handle = ctypes.c_void_p()
        nt_create_file = ntdll.NtCreateFile
        nt_create_file.argtypes = [
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
            ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IoStatusBlock),
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
        ]
        nt_create_file.restype = ctypes.c_long
        # FILE_LIST_DIRECTORY is a data-access bit: without it, Windows does
        # not apply the no-FILE_SHARE_DELETE guard to directory rename opens.
        desired_access = (
            cls._READ_ATTRIBUTES
            | cls._READ_CONTROL
            | cls._FILE_LIST_DIRECTORY
            | 0x00100000  # SYNCHRONIZE
        )
        share_access = cls._SHARE_READ | cls._SHARE_WRITE
        create_options = (
            cls._FILE_DIRECTORY_FILE
            | cls._FILE_OPEN_REPARSE_POINT
            | cls._FILE_SYNCHRONOUS_IO_NONALERT
        )
        try:
            status = nt_create_file(
                ctypes.byref(result_handle), desired_access,
                ctypes.byref(attributes), ctypes.byref(io_status),
                None, 0x10, share_access, cls._FILE_CREATE,
                create_options, None, 0,
            )
            if status < 0:
                unsigned_status = status & 0xFFFFFFFF
                if unsigned_status != cls._STATUS_OBJECT_NAME_COLLISION:
                    raise PlatformStorageUnavailable(
                        "Windows SQLite state directory could not be created securely."
                    )
                # Another initializer may have won the create race. Open the
                # existing child relative to the same pinned parent and verify
                # its descriptor; never repair or replace it.
                attributes.SecurityDescriptor = None
                status = nt_create_file(
                    ctypes.byref(result_handle), desired_access,
                    ctypes.byref(attributes), ctypes.byref(io_status),
                    None, 0, share_access, cls._FILE_OPEN,
                    create_options, None, 0,
                )
                if status < 0:
                    raise PlatformStorageUnavailable(
                        "Existing Windows SQLite state directory could not be opened safely."
                    )
            return pywintypes.HANDLE(result_handle.value)
        finally:
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            kernel.LocalFree(descriptor)

    @classmethod
    def _verify_file_security(cls, handle, sid) -> None:
        """Require an explicit protected owner-only DACL and the expected owner."""
        security = cls._api()[5]
        desc = security.GetSecurityInfo(
            handle,
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION,
        )
        if desc.GetSecurityDescriptorOwner() != sid:
            raise PlatformStorageUnavailable(
                "Windows SQLite entry owner SID is not current user."
            )
        dacl = desc.GetSecurityDescriptorDacl()
        if dacl is None or dacl.GetAceCount() != 1:
            raise PlatformStorageUnavailable(
                "SQLite database or sidecar DACL is not private."
            )
        header, mask, ace_sid = cls._read_conventional_allow_ace(dacl)
        if (
            header[0] != security.ACCESS_ALLOWED_ACE_TYPE
            or header[1] != 0
            or mask != cls._ALL_ACCESS
            or ace_sid != sid
        ):
            raise PlatformStorageUnavailable(
                "SQLite database or sidecar DACL is not the explicit owner-only ACL."
            )
        control, _revision = desc.GetSecurityDescriptorControl()
        if not control & security.SE_DACL_PROTECTED:
            raise PlatformStorageUnavailable(
                "SQLite database or sidecar DACL is not protected."
            )

    @classmethod
    def _create_or_open_private_file(cls, path: Path, sid) -> None:
        """Create each SQLite file-set member with an explicit owner/DACL.

        SQLite then opens an already-created file. This avoids relying on the
        process token's default owner, which can differ from TokenUser.
        Existing entries are only opened and verified; they are never repaired.
        """
        ctypes, pywintypes, _api, _con, file, security = cls._api()
        sid_text = security.ConvertSidToStringSid(sid)
        sddl = f"O:{sid_text}D:P(A;;0x001F01FF;;;{sid_text})"
        descriptor = ctypes.c_void_p()
        advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        convert.restype = ctypes.c_int
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise PlatformStorageUnavailable(
                "Secure Windows SQLite file security descriptor could not be created."
            )

        class SecurityAttributes(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("nLength", ctypes.c_ulong),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_int),
            ]

        attributes = SecurityAttributes(
            ctypes.sizeof(SecurityAttributes), descriptor, 0
        )
        create_file = kernel.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(SecurityAttributes),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        invalid_handle = ctypes.c_void_p(-1).value
        access = 0x80000000 | 0x40000000 | cls._READ_CONTROL
        sharing = cls._SHARE_READ | cls._SHARE_WRITE | cls._SHARE_DELETE
        flags = 0x80 | cls._OPEN_REPARSE_POINT
        handle_value = create_file(
            str(path), access, sharing, ctypes.byref(attributes), 1, flags, None
        )
        if handle_value in (None, 0, invalid_handle):
            error = ctypes.get_last_error()
            if error not in (80, 183):  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS
                kernel.LocalFree.argtypes = [ctypes.c_void_p]
                kernel.LocalFree.restype = ctypes.c_void_p
                kernel.LocalFree(descriptor)
                raise PlatformStorageUnavailable(
                    "Windows SQLite database or sidecar could not be created securely."
                )
            handle_value = create_file(
                str(path), access, sharing, None, cls._OPEN_EXISTING, flags, None
            )
            if handle_value in (None, 0, invalid_handle):
                kernel.LocalFree.argtypes = [ctypes.c_void_p]
                kernel.LocalFree.restype = ctypes.c_void_p
                kernel.LocalFree(descriptor)
                raise PlatformStorageUnavailable(
                    "Existing Windows SQLite database or sidecar could not be opened safely."
                )
        handle = pywintypes.HANDLE(handle_value)
        try:
            cls._check_type(handle, False)
            cls._verify_file_security(handle, sid)
        finally:
            try:
                file.CloseHandle(handle)
            finally:
                kernel.LocalFree.argtypes = [ctypes.c_void_p]
                kernel.LocalFree.restype = ctypes.c_void_p
                kernel.LocalFree(descriptor)

    @classmethod
    def _drive_type(cls, drive_root: str) -> int:
        ctypes = cls._api()[0]
        kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        get_drive_type = kernel.GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint32
        return int(get_drive_type(drive_root))

    @classmethod
    def _require_fixed_local_drive(cls, path: Path) -> None:
        if not path.drive or path.drive.startswith("\\\\"):
            raise PlatformStorageUnavailable("Windows SQLite path must be on a local drive.")
        drive_root = path.drive + "\\"
        if cls._drive_type(drive_root) != 3:  # DRIVE_FIXED only; reject mapped/network/removable.
            raise PlatformStorageUnavailable(
                "Windows SQLite path must be on a fixed local drive."
            )

    @staticmethod
    def _wait_for_mutex(wait_function, handle, timeout_ms: int) -> int:
        """Small seam for deterministic contention tests around the native wait."""
        return int(wait_function(handle, timeout_ms))

    @classmethod
    def _directory_identity(cls, directory_handle) -> tuple[int, int]:
        """Return the stable NTFS volume/file identity from a pinned directory handle."""
        file = cls._api()[4]
        try:
            info = file.GetFileInformationByHandle(directory_handle)
            if not isinstance(info, tuple) or len(info) < 10:
                raise ValueError("unexpected BY_HANDLE_FILE_INFORMATION shape")
            volume_serial = int(info[4])
            file_index = (int(info[8]) << 32) | int(info[9])
        except (TypeError, ValueError, IndexError, OverflowError):
            raise PlatformStorageUnavailable(
                "Windows SQLite state directory identity could not be verified."
            ) from None
        return volume_serial, file_index

    @classmethod
    @contextmanager
    def _database_mutex(cls, directory_handle, sid):
        """Serialize leases by validated directory identity, not path spelling.

        A per-user, per-directory-identity mutex makes long and 8.3 short
        path aliases converge on the same lock. The directory must already
        be pinned and verified before this mutex is acquired.
        """
        ctypes = cls._api()[0]
        security = cls._api()[5]
        sid_text = security.ConvertSidToStringSid(sid)
        volume_serial, file_index = cls._directory_identity(directory_handle)
        identity = f"{volume_serial:08x}\\0{file_index:016x}"
        key = hashlib.sha256(f"{sid_text}\\0{identity}".encode()).hexdigest()
        mutex_name = f"Global\\AgentBackend.SQLiteJobStore.{key}"

        kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)

        class SecurityAttributes(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, object]]] = [
                ("nLength", ctypes.c_ulong),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_int),
            ]

        sid_text = security.ConvertSidToStringSid(sid)
        sddl = f"O:{sid_text}D:P(A;;0x001F0001;;;{sid_text})(A;;0x001F0001;;;SY)"
        descriptor = ctypes.c_void_p()
        convert = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        convert.restype = ctypes.c_int
        if not convert(sddl, 1, ctypes.byref(descriptor), None):
            raise PlatformStorageUnavailable(
                "Windows SQLite mutex security descriptor could not be created."
            )
        attributes = SecurityAttributes(
            ctypes.sizeof(SecurityAttributes), descriptor, 0
        )

        create_mutex = kernel.CreateMutexW
        create_mutex.argtypes = [
            ctypes.POINTER(SecurityAttributes), ctypes.c_int, ctypes.c_wchar_p
        ]
        create_mutex.restype = ctypes.c_void_p
        wait_for_single_object = kernel.WaitForSingleObject
        wait_for_single_object.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        wait_for_single_object.restype = ctypes.c_uint32
        release_mutex = kernel.ReleaseMutex
        release_mutex.argtypes = [ctypes.c_void_p]
        release_mutex.restype = ctypes.c_int
        close_handle = kernel.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int

        try:
            handle = create_mutex(ctypes.byref(attributes), 0, mutex_name)
        finally:
            local_free = kernel.LocalFree
            local_free.argtypes = [ctypes.c_void_p]
            local_free.restype = ctypes.c_void_p
            local_free(descriptor)
        if not handle:
            raise PlatformStorageUnavailable(
                "Windows SQLite initialization mutex could not be created."
            )
        acquired = False
        try:
            wait_result = cls._wait_for_mutex(wait_for_single_object, handle, 5_000)
            if wait_result == 0x00000102:  # WAIT_TIMEOUT
                raise PlatformStorageUnavailable(
                    "Windows SQLite initialization mutex acquisition timed out."
                )
            if wait_result not in (0x00000000, 0x00000080):
                raise PlatformStorageUnavailable(
                    "Windows SQLite initialization mutex could not be acquired."
                )
            acquired = True
            yield
        finally:
            release_succeeded = True
            close_succeeded = True
            try:
                if acquired:
                    release_succeeded = bool(release_mutex(handle))
            finally:
                close_succeeded = bool(close_handle(handle))
            if not release_succeeded or not close_succeeded:
                raise PlatformStorageUnavailable(
                    "Windows SQLite initialization mutex could not be released safely."
                )

    @staticmethod
    def _is_native_error(exc: Exception) -> bool:
        """Identify pywin32 exceptions without translating application errors."""
        return type(exc).__module__ == "pywintypes"

    @contextmanager
    def protect_database(self, path: Path):
        try:
            with self._protect_database(path) as lease:
                yield lease
        except PlatformStorageUnavailable:
            raise
        except Exception as exc:
            if self._is_native_error(exc):
                raise PlatformStorageUnavailable(
                    "Windows security APIs failed while acquiring or releasing the SQLite lease."
                ) from None
            raise

    @contextmanager
    def _protect_database(self, path: Path):
        if os.name != "nt" or not isinstance(path, Path) or not path.is_absolute():
            raise PlatformStorageUnavailable("Windows SQLite path is unavailable or not absolute.")
        self._require_fixed_local_drive(path)
        _ctypes, pywintypes, _api, _con, file, _security = self._api()
        sid = self._sid()
        with ExitStack() as stack:
            if path.parent.parent == path.parent:
                raise PlatformStorageUnavailable(
                    "Windows SQLite database must be inside a dedicated state directory."
                )
            for component in reversed(path.parent.parents):
                try:
                    handle = file.CreateFile(
                        str(component),
                        self._READ_ATTRIBUTES
                        | self._READ_CONTROL
                        | self._FILE_LIST_DIRECTORY,
                        self._SHARE_READ | self._SHARE_WRITE,
                        None, self._OPEN_EXISTING,
                        self._BACKUP_SEMANTICS | self._OPEN_REPARSE_POINT, None,
                    )
                except pywintypes.error:
                    raise PlatformStorageUnavailable(
                        "Windows SQLite ancestor directory could not be pinned."
                    ) from None
                stack.callback(file.CloseHandle, handle)
                self._check_type(handle, True)

            try:
                parent_handle = file.CreateFile(
                    str(path.parent.parent),
                    self._READ_ATTRIBUTES
                    | self._READ_CONTROL
                    | self._FILE_ADD_SUBDIRECTORY,
                    self._SHARE_READ | self._SHARE_WRITE,
                    None, self._OPEN_EXISTING,
                    self._BACKUP_SEMANTICS | self._OPEN_REPARSE_POINT, None,
                )
            except pywintypes.error:
                raise PlatformStorageUnavailable(
                    "Windows SQLite parent directory could not be pinned safely."
                ) from None
            stack.callback(file.CloseHandle, parent_handle)
            self._check_type(parent_handle, True)

            directory_handle = self._create_or_open_private_directory(
                parent_handle, path.parent.name, sid
            )
            stack.callback(file.CloseHandle, directory_handle)
            self._check_type(directory_handle, True)
            self._verify_directory(directory_handle, sid)
            # The pinned, verified directory handle supplies a stable volume
            # and file ID. Acquire the mutex only now so path aliases cannot
            # bypass same-directory serialization.
            stack.enter_context(self._database_mutex(directory_handle, sid))
            lease = _WindowsDatabaseProtectionLease(path, sid)
            # Pre-create the complete SQLite file set with an explicit owner
            # and protected DACL. SQLite never gets to create an entry using
            # the process token's potentially different default owner.
            for entry in lease._entries():
                self._create_or_open_private_file(entry, sid)
            lease.verify()
            try:
                yield lease
            finally:
                lease.verify()


class _WindowsDatabaseProtectionLease:
    def __init__(self, path: Path, sid):
        self._path = path
        self._sid = sid

    def _entries(self):
        return (
            self._path,
            Path(f"{self._path}-wal"),
            Path(f"{self._path}-shm"),
            Path(f"{self._path}-journal"),
        )

    def verify(self):
        adapter = WindowsSecureStorage
        _ctypes, _pywintypes, _api, _con, file, _security = adapter._api()
        try:
            for entry in self._entries():
                access = adapter._READ_ATTRIBUTES | adapter._READ_CONTROL
                try:
                    handle = file.CreateFile(
                        str(entry), access,
                        adapter._SHARE_READ | adapter._SHARE_WRITE | adapter._SHARE_DELETE,
                        None, adapter._OPEN_EXISTING, adapter._OPEN_REPARSE_POINT, None,
                    )
                except Exception as exc:
                    if adapter._is_native_error(exc):
                        code = getattr(exc, "winerror", None)
                        if code is None and getattr(exc, "args", None):
                            code = exc.args[0]
                        if code in (2, 3):
                            continue
                        raise PlatformStorageUnavailable(
                            "SQLite sidecar security could not be checked."
                        ) from None
                    raise
                try:
                    adapter._check_type(handle, False)
                    # Every file-set member was created or opened and
                    # verified before SQLite was allowed to connect.
                    adapter._verify_file_security(handle, self._sid)
                finally:
                    file.CloseHandle(handle)
        except PlatformStorageUnavailable:
            raise
        except Exception as exc:
            if adapter._is_native_error(exc):
                raise PlatformStorageUnavailable(
                    "Windows security APIs failed while verifying SQLite files."
                ) from None
            raise


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
        # The Windows adapter is enabled only after the dedicated native
        # integration suite is exercised in the Windows CI workflow. It pins
        # local directory handles, rejects reparse points, verifies current-user
        # ownership and protected owner-only DACLs for the database and sidecars,
        # and serializes leases with a SID-scoped, directory-identity mutex.
        return WindowsSecureStorage()
    if current == "darwin":
        raise PlatformStorageUnavailable(
            "macOS job-store storage is disabled pending native ACL and "
            "handle-based path-race protections."
        )
    raise PlatformStorageUnavailable(
        f"Job-store storage is not supported on platform {current!r}."
    )
