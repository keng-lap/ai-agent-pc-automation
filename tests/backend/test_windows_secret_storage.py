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
        _parent, sid = store._parent_handles(stack)
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


def test_windows_secret_file_pins_parent_directory_against_rename(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir()
    store = WindowsSecretFile(directory / "authenticator.json")
    store.create_exclusive(b"encrypted")

    with ExitStack() as stack:
        store._parent_handles(stack)
        with pytest.raises(OSError):
            os.rename(directory, directory.with_name("renamed"))
