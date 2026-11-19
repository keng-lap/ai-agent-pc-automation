import os
import sqlite3

import pytest

from agent_backend.windows_sqlite_storage import (
    WindowsSQLiteStorage,
    WindowsSQLiteStorageError,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows ACL integration")


def test_windows_sqlite_storage_secures_database_and_wal_sidecars(tmp_path):
    database = tmp_path / "private" / "approval.sqlite3"
    storage = WindowsSQLiteStorage(database)
    connection = None
    try:
        storage.prepare_database_path(database)
        storage._verify_directory_dacl(
            storage._directory_handle,
            storage._sid,
        )

        connection = sqlite3.connect(database)
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert mode.lower() == "wal"
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence(value) VALUES ('private')")
        connection.commit()

        for suffix in ("", "-wal", "-shm"):
            path = type(database)(str(database) + suffix)
            if path.exists():
                storage._verify_inherited_file_dacl(path, storage._sid)

        storage.finalize_database_file(database)
        for suffix in ("", "-wal", "-shm"):
            path = type(database)(str(database) + suffix)
            if path.exists():
                assert storage._secure_existing_file(path, storage._sid)
        assert database.is_file()
    finally:
        if connection is not None:
            connection.close()
        storage.close()


def test_windows_sqlite_storage_pins_directory_against_rename(tmp_path):
    import pywintypes
    import win32file

    database = tmp_path / "private" / "approval.sqlite3"
    storage = WindowsSQLiteStorage(database)
    storage.prepare_database_path(database)
    try:
        with pytest.raises(pywintypes.error):
            win32file.MoveFile(
                str(database.parent),
                str(database.parent.with_name("renamed-private")),
            )
    finally:
        storage.close()


def test_windows_sqlite_storage_rejects_existing_database_reparse_point(tmp_path):
    database = tmp_path / "private" / "approval.sqlite3"
    database.parent.mkdir()
    target = tmp_path / "target.sqlite3"
    target.touch()
    try:
        os.symlink(target, database)
    except OSError:
        pytest.skip("The Windows runner does not permit creating file symlinks")

    storage = WindowsSQLiteStorage(database)
    with pytest.raises(WindowsSQLiteStorageError, match="reparse point"):
        storage.prepare_database_path(database)
    storage.close()
