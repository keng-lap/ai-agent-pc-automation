import os
from contextlib import ExitStack

import pytest

from agent_backend.windows_secret_storage import (
    WindowsSecretFile,
    WindowsSecretStorageError,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows security API integration")


def test_windows_secret_file_uses_owner_only_dacl_and_handle_io(tmp_path):
    store = WindowsSecretFile(tmp_path / "private" / "authenticator.json")

    store.create_exclusive(b"first-encrypted-envelope")

    assert store.exists()
    assert store.read() == b"first-encrypted-envelope"
    with pytest.raises(FileExistsError):
        store.create_exclusive(b"must-not-overwrite")

    store.replace(b"replacement-envelope")
    assert store.read() == b"replacement-envelope"

    with ExitStack() as stack:
        parent_handle, sid = store._parent_handles(stack)
        store._verify_owner_only_dacl(parent_handle, sid)
        handle = store._open_file(stack, sid, create=False)
        store._verify_owner_only_dacl(handle, sid)


def test_windows_secret_file_rejects_reparse_point_ancestor(tmp_path):
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    link_directory = tmp_path / "linked"
    try:
        os.symlink(real_directory, link_directory, target_is_directory=True)
    except OSError:
        pytest.skip("The Windows runner does not permit creating directory symlinks")

    store = WindowsSecretFile(link_directory / "authenticator.json")
    with pytest.raises(WindowsSecretStorageError, match="reparse point"):
        store.exists()


def test_windows_secret_file_denies_rename_while_handle_is_open(tmp_path):
    import pywintypes
    import win32file

    store = WindowsSecretFile(tmp_path / "private" / "authenticator.json")
    store.create_exclusive(b"encrypted")

    with ExitStack() as stack:
        _parent, sid = store._parent_handles(stack)
        store._open_file(stack, sid, create=False)
        with pytest.raises(pywintypes.error):
            win32file.MoveFile(
                str(store._path),
                str(store._path.with_name("renamed.json")),
            )

def test_windows_secret_file_repairs_extra_dacl_ace_for_verified_owner(tmp_path):
    import win32con
    import win32file
    import win32security

    store = WindowsSecretFile(tmp_path / "private" / "authenticator.json")
    store.create_exclusive(b"encrypted")

    handle = win32file.CreateFile(
        str(store._path),
        win32con.READ_CONTROL | win32con.WRITE_DAC,
        win32con.FILE_SHARE_READ,
        None,
        win32con.OPEN_EXISTING,
        0x00200000,
        None,
    )
    try:
        owner = WindowsSecretFile._current_user_sid()
        everyone = win32security.CreateWellKnownSid(
            win32security.WinWorldSid, None
        )
        acl = win32security.ACL()
        acl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION, 0, 0x001F01FF, owner
        )
        acl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION, 0, 0x00000001, everyone
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
    finally:
        win32file.CloseHandle(handle)

    assert store.read() == b"encrypted"
    with ExitStack() as stack:
        _parent, sid = store._parent_handles(stack)
        handle = win32file.CreateFile(
            str(store._path),
            win32con.READ_CONTROL,
            win32con.FILE_SHARE_READ,
            None,
            win32con.OPEN_EXISTING,
            0x00200000,
            None,
        )
        try:
            WindowsSecretFile._verify_owner_only_dacl(handle, sid)
        finally:
            win32file.CloseHandle(handle)


def test_windows_secret_file_rejects_file_reparse_point(tmp_path):
    target = WindowsSecretFile(tmp_path / "private" / "target.bin")
    target.create_exclusive(b"not-an-authenticator")
    link = tmp_path / "private" / "authenticator.json"
    try:
        os.symlink(target._path, link)
    except OSError:
        pytest.skip("The Windows runner does not permit creating file symlinks")

    store = WindowsSecretFile(link)
    with pytest.raises(WindowsSecretStorageError, match="reparse point"):
        store.read()



def test_create_file_is_removed_if_owner_dacl_setup_fails(tmp_path, monkeypatch):
    store = WindowsSecretFile(tmp_path / "private" / "authenticator.json")
    with ExitStack() as parent_stack:
        _parent, sid = store._parent_handles(parent_stack)

        def fail_dacl(_cls, *_args, **_kwargs):
            raise WindowsSecretStorageError("simulated DACL failure")

        monkeypatch.setattr(
            WindowsSecretFile,
            "_set_owner_only_dacl",
            classmethod(fail_dacl),
        )
        with ExitStack() as file_stack:
            with pytest.raises(WindowsSecretStorageError, match="simulated DACL failure"):
                store._open_file(file_stack, sid, create=True)

    assert not store._path.exists()
