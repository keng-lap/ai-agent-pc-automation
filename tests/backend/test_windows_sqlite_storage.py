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
    setup = WindowsSQLiteStorage(database)
    setup.prepare_database_path(database)
    setup.close()

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


def test_windows_sqlite_storage_secures_rollback_journal(tmp_path):
    database = tmp_path / "private" / "approval.sqlite3"
    storage = WindowsSQLiteStorage(database)
    connection = None
    try:
        storage.prepare_database_path(database)
        connection = sqlite3.connect(database)
        mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        assert mode.lower() == "delete"
        connection.execute("CREATE TABLE evidence (value TEXT NOT NULL)")
        connection.commit()

        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO evidence(value) VALUES ('private')")
        journal = type(database)(str(database) + "-journal")
        assert journal.exists()
        storage._verify_inherited_file_dacl(journal, storage._sid)

        storage.finalize_database_file(database)
        _pywintypes, win32file, _security = storage._api()
        handle = win32file.CreateFile(
            str(journal),
            0x80000000 | 0x00020000,
            0x00000001 | 0x00000002,
            None,
            3,
            0x00000080 | 0x00200000,
            None,
        )
        try:
            storage._verify_file_dacl(handle, storage._sid)
        finally:
            win32file.CloseHandle(handle)
        connection.rollback()
    finally:
        if connection is not None:
            connection.close()
        storage.close()
