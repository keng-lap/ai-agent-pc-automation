"""Handle-based Windows secret-file storage with owner-only DACLs.

This adapter opens and holds every directory component without FILE_SHARE_DELETE,
rejects reparse points, verifies the current-user owner SID, and performs file I/O
through verified handles. It deliberately fails closed if pywin32 is unavailable.
"""

import ctypes
import os
import secrets
from contextlib import ExitStack
from pathlib import Path


_FILE_READ_ATTRIBUTES = 0x00000080
_FILE_ADD_FILE = 0x00000002
_FILE_ALL_ACCESS = 0x001F01FF
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_CREATE_NEW = 1
_READ_CONTROL = 0x00020000
_WRITE_DAC = 0x00040000
_WRITE_OWNER = 0x00080000


class WindowsSecretStorageError(RuntimeError):
    """Windows secret storage could not be proven safe."""


class WindowsSecretFile:
    """Secure one secret file beneath a current-user-only directory."""

    _MAX_BYTES = 16 * 1024

    def __init__(self, path: Path) -> None:
        if os.name != "nt":
            raise WindowsSecretStorageError("Windows secret storage is unavailable.")
        if not isinstance(path, Path):
            raise TypeError("secret path must be a pathlib.Path")
        self._path = Path(os.path.abspath(path))

    @staticmethod
    def _api():
        try:
            import pywintypes
            import win32api
            import win32con
            import win32file
            import win32security
        except ImportError:
            raise WindowsSecretStorageError(
                "Windows security APIs are unavailable."
            ) from None
        return win32api, win32con, win32file, win32security, pywintypes

    @classmethod
    def _current_user_sid(cls):
        win32api, win32con, _win32file, win32security, _pywintypes = cls._api()
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        try:
            return win32security.GetTokenInformation(
                token, win32security.TokenUser
            )[0]
        finally:
            win32api.CloseHandle(token)

    @staticmethod
    def _close(stack: ExitStack, handle) -> None:
        win32file = WindowsSecretFile._api()[2]
        stack.callback(win32file.CloseHandle, handle)

    @classmethod
    def _verify_not_reparse(cls, handle, *, directory: bool) -> None:
        _win32api, _win32con, win32file, _win32security, _pywintypes = cls._api()
        attributes = win32file.GetFileInformationByHandle(handle)[0]
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsSecretStorageError("Secret path contains a reparse point.")
        if directory and not attributes & _FILE_ATTRIBUTE_DIRECTORY:
            raise WindowsSecretStorageError("Secret parent is not a directory.")
        if not directory and attributes & _FILE_ATTRIBUTE_DIRECTORY:
            raise WindowsSecretStorageError("Secret path is not a regular file.")

    @classmethod
    def _set_owner_only_dacl(cls, handle, sid, *, allow_owner_change: bool) -> None:
        win32security = cls._api()[3]
        descriptor = win32security.GetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != sid:
            if not allow_owner_change:
                raise WindowsSecretStorageError("Secret path owner SID is not current user.")
            win32security.SetSecurityInfo(
                handle,
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
                sid,
                None,
                None,
                None,
            )
        acl = win32security.ACL()
        acl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            _FILE_ALL_ACCESS,
            sid,
        )
        win32security.SetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        cls._verify_owner_only_dacl(handle, sid)

    @classmethod
    def _verify_owner_only_dacl(cls, handle, sid) -> None:
        win32security = cls._api()[3]
        descriptor = win32security.GetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != sid:
            raise WindowsSecretStorageError("Secret path owner SID is not current user.")
        dacl = descriptor.GetSecurityDescriptorDacl()
        if dacl is None or dacl.GetAceCount() != 1:
            raise WindowsSecretStorageError("Secret path DACL is not owner-only.")
        header, mask, ace_sid = dacl.GetAce(0)
        if (
            header[0] != win32security.ACCESS_ALLOWED_ACE_TYPE
            or header[1] != 0
            or mask != _FILE_ALL_ACCESS
            or ace_sid != sid
        ):
            raise WindowsSecretStorageError("Secret path DACL is not owner-only.")
        control, _revision = descriptor.GetSecurityDescriptorControl()
        if not control & win32security.SE_DACL_PROTECTED:
            raise WindowsSecretStorageError("Secret path DACL inheritance is not disabled.")

    @classmethod
    def _open_directory(
        cls,
        path: Path,
        *,
        final: bool,
        created: bool,
        sid,
        stack: ExitStack,
    ):
        win32file = cls._api()[2]
        win32security = cls._api()[3]
        access = _FILE_READ_ATTRIBUTES | _READ_CONTROL
        if final:
            access |= _FILE_ADD_FILE | _WRITE_DAC | _WRITE_OWNER
        try:
            handle = win32file.CreateFile(
                str(path),
                access,
                _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                None,
                _OPEN_EXISTING,
                _FILE_FLAG_BACKUP_SEMANTICS
                | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        except cls._api()[4].error as exc:
            error_code = getattr(exc, "winerror", None)
            if error_code is None and getattr(exc, "args", None):
                error_code = exc.args[0]
            if error_code in (2, 3):
                raise FileNotFoundError from None
            raise WindowsSecretStorageError(
                f"Secret directory could not be opened safely (Win32 error {error_code})."
            ) from None
        cls._close(stack, handle)
        cls._verify_not_reparse(handle, directory=True)
        if final:
            descriptor = win32security.GetSecurityInfo(
                handle,
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
            )
            if descriptor.GetSecurityDescriptorOwner() != sid and not created:
                raise WindowsSecretStorageError(
                    "Secret directory owner SID is not current user."
                )
            # Repair an overly broad/inherited DACL only when the directory
            # owner is already the current user; never take ownership of an
            # existing directory.
            cls._set_owner_only_dacl(
                handle,
                sid,
                allow_owner_change=created,
            )
        return handle

    def _parent_handles(self, stack: ExitStack):
        parent = self._path.parent
        if not parent.is_absolute() or not parent.drive or parent.drive.startswith("\\\\"):
            raise WindowsSecretStorageError("Secret path must be an absolute local path.")
        sid = self._current_user_sid()
        components = [*reversed(parent.parents), parent]
        final_handle = None
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        create_directory = kernel32.CreateDirectoryW
        create_directory.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
        create_directory.restype = ctypes.c_int
        for index, component in enumerate(components):
            final = index == len(components) - 1
            created = False
            try:
                final_handle = self._open_directory(
                    component,
                    final=final,
                    created=False,
                    sid=sid,
                    stack=stack,
                )
            except FileNotFoundError:
                if not create_directory(str(component), None):
                    error = ctypes.get_last_error()
                    if error != 183:  # ERROR_ALREADY_EXISTS: verify the winner below.
                        raise WindowsSecretStorageError(
                            f"Secret directory could not be created (Win32 error {error})."
                        ) from None
                else:
                    created = True
                final_handle = self._open_directory(
                    component,
                    final=final,
                    created=created,
                    sid=sid,
                    stack=stack,
                )
        return final_handle, sid

    def _open_file(self, stack: ExitStack, sid, *, create: bool):
        win32file = self._api()[2]
        pywintypes = self._api()[4]
        disposition = _CREATE_NEW if create else _OPEN_EXISTING
        access = _GENERIC_READ | _READ_CONTROL
        if create:
            access |= _GENERIC_WRITE | _WRITE_DAC | _WRITE_OWNER
        try:
            handle = win32file.CreateFile(
                str(self._path),
                access,
                _FILE_SHARE_READ,
                None,
                disposition,
                _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        except pywintypes.error as exc:
            error_code = getattr(exc, "winerror", None)
            if error_code is None and getattr(exc, "args", None):
                error_code = exc.args[0]
            if create and error_code in (80, 183):
                raise FileExistsError from None
            if not create and error_code in (2, 3):
                raise FileNotFoundError from None
            raise WindowsSecretStorageError(
                f"Secret file could not be opened safely (Win32 error {error_code})."
            ) from None
        self._close(stack, handle)
        self._verify_not_reparse(handle, directory=False)
        if create:
            self._set_owner_only_dacl(
                handle,
                sid,
                allow_owner_change=True,
            )
        else:
            # Existing secret files are immutable from a trust-policy
            # perspective: verify their ACL, but never attempt to repair it.
            # Repair would require WRITE_DAC and could mask tampering.
            self._verify_owner_only_dacl(handle, sid)
        return handle

    def exists(self) -> bool:
        with ExitStack() as stack:
            _parent, sid = self._parent_handles(stack)
            try:
                self._open_file(stack, sid, create=False)
            except FileNotFoundError:
                return False
            return True

    def create_exclusive(self, payload: bytes) -> None:
        if not isinstance(payload, bytes) or not 0 < len(payload) <= self._MAX_BYTES:
            raise WindowsSecretStorageError("Secret payload size is invalid.")
        with ExitStack() as stack:
            _parent, sid = self._parent_handles(stack)
            handle = self._open_file(stack, sid, create=True)
            win32file = self._api()[2]
            error, written = win32file.WriteFile(handle, payload)
            if error or written != len(payload):
                raise WindowsSecretStorageError("Secret file write was incomplete.")
            win32file.FlushFileBuffers(handle)

    def read(self) -> bytes:
        with ExitStack() as stack:
            _parent, sid = self._parent_handles(stack)
            handle = self._open_file(stack, sid, create=False)
            win32file = self._api()[2]
            info = win32file.GetFileInformationByHandle(handle)
            size = (info[5] << 32) | info[6]
            if not 0 < size <= self._MAX_BYTES:
                raise WindowsSecretStorageError("Secret file size is invalid.")
            error, payload = win32file.ReadFile(handle, self._MAX_BYTES + 1)
            if error or len(payload) != size:
                raise WindowsSecretStorageError("Secret file read was incomplete.")
            return payload

    def replace(self, payload: bytes) -> None:
        if not isinstance(payload, bytes) or not 0 < len(payload) <= self._MAX_BYTES:
            raise WindowsSecretStorageError("Secret payload size is invalid.")

        temporary_name = f".{self._path.name}.{secrets.token_hex(16)}.tmp"
        temporary = self._path.with_name(temporary_name)
        with ExitStack() as parent_stack:
            _parent_handle, sid = self._parent_handles(parent_stack)
            # Verify the destination while its parent directory is pinned, then
            # close that file handle before asking Windows to replace it.
            with ExitStack() as check:
                _parent, check_sid = self._parent_handles(check)
                self._open_file(check, check_sid, create=False)

            WindowsSecretFile(temporary).create_exclusive(payload)

            win32file = self._api()[2]
            pywintypes = self._api()[4]
            try:
                with ExitStack() as rename_stack:
                    source = win32file.CreateFile(
                        str(temporary),
                        _GENERIC_READ | _GENERIC_WRITE | 0x00010000,  # DELETE
                        _FILE_SHARE_READ,
                        None,
                        _OPEN_EXISTING,
                        _FILE_FLAG_OPEN_REPARSE_POINT,
                        None,
                    )
                    self._close(rename_stack, source)
                    self._verify_not_reparse(source, directory=False)
                    self._verify_owner_only_dacl(source, sid)

                    # SetFileInformationByHandle on supported Windows runners
                    # rejects a non-null RootDirectory (ERROR_INVALID_PARAMETER).
                    # Use the absolute destination while every verified parent
                    # directory remains open without FILE_SHARE_DELETE; this
                    # prevents path-component replacement during the rename.
                    name_bytes = str(self._path).encode("utf-16-le")
                    class _RenameFlags(ctypes.Union):
                        _fields_ = [
                            ("ReplaceIfExists", ctypes.c_ubyte),
                            ("Flags", ctypes.c_uint32),
                        ]

                    class _FileRenameInfo(ctypes.Structure):
                        _fields_ = [
                            ("RenameFlags", _RenameFlags),
                            ("RootDirectory", ctypes.c_void_p),
                            ("FileNameLength", ctypes.c_uint32),
                            ("FileName", ctypes.c_wchar * 1),
                        ]

                    name_offset = _FileRenameInfo.FileName.offset
                    buffer = ctypes.create_string_buffer(name_offset + len(name_bytes))
                    info = _FileRenameInfo.from_buffer(buffer)
                    info.RenameFlags.ReplaceIfExists = 1
                    info.RootDirectory = None
                    info.FileNameLength = len(name_bytes)
                    ctypes.memmove(
                        ctypes.addressof(buffer) + name_offset,
                        name_bytes,
                        len(name_bytes),
                    )

                    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
                    set_file_info = kernel32.SetFileInformationByHandle
                    set_file_info.argtypes = [
                        ctypes.c_void_p,
                        ctypes.c_int,
                        ctypes.c_void_p,
                        ctypes.c_uint32,
                    ]
                    set_file_info.restype = ctypes.c_int
                    if not set_file_info(
                        int(source),
                        3,  # FileRenameInfo
                        ctypes.byref(buffer),
                        ctypes.sizeof(buffer),
                    ):
                        error = ctypes.get_last_error()
                        raise WindowsSecretStorageError(
                            f"Handle-relative secret replacement failed (Win32 error {error})."
                        )
            except (OSError, pywintypes.error):
                # Do not fall back to a path-based rename or deletion. A
                # leftover random temporary file is safer than an unpinned
                # path operation; the next successful maintenance pass can
                # report it for manual cleanup.
                raise WindowsSecretStorageError(
                    "Secret replacement could not be completed safely."
                ) from None

            # Reopen and verify the replacement through the pinned directory.
            self._open_file(parent_stack, sid, create=False)
