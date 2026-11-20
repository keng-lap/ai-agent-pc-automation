import sqlite3
from concurrent.futures import ThreadPoolExecutor
import stat
import sys
from pathlib import Path

import pytest

from agent_backend.job_store import SQLiteJobStore
from agent_backend.platform_storage import (
    LinuxSecureStorage,
    PlatformStorageUnavailable,
    WindowsSecureStorage,
    create_platform_secure_storage,
)


def test_linux_platform_selects_linux_secure_storage():
    assert isinstance(
        create_platform_secure_storage(platform="linux"), LinuxSecureStorage
    )


@pytest.mark.parametrize("platform", ["win32", "darwin", "freebsd"])
def test_unreviewed_platforms_fail_closed(platform):
    with pytest.raises(PlatformStorageUnavailable):
        create_platform_secure_storage(platform=platform)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux ownership checks require geteuid")
def test_linux_adapter_creates_private_state_directory_and_database(tmp_path):
    adapter = LinuxSecureStorage()
    database = tmp_path / "private-state" / "jobs.sqlite3"

    with adapter.protect_database(database) as lease:
        database.touch()
        lease.verify()

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform != "linux", reason="Linux adapter test")
def test_linux_adapter_rejects_symlink_database_path(tmp_path):
    adapter = LinuxSecureStorage()
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "private-state" / "jobs.sqlite3"
    link.parent.mkdir()
    link.symlink_to(target)

    with pytest.raises(PlatformStorageUnavailable, match="symbolic link"):
        adapter.prepare_database_path(link)



@pytest.mark.skipif(sys.platform != "linux", reason="Linux adapter test")
def test_linux_lease_rejects_unsafe_sqlite_sidecar(tmp_path):
    adapter = LinuxSecureStorage()
    database = tmp_path / "private-state" / "jobs.sqlite3"

    with adapter.protect_database(database) as lease:
        database.touch()
        sidecar = database.with_name(database.name + "-wal")
        sidecar.symlink_to(database)

        with pytest.raises(PlatformStorageUnavailable, match="sidecar"):
            lease.verify()
        sidecar.unlink()




@pytest.mark.skipif(sys.platform != "win32", reason="Windows native ACL integration test")
def test_windows_lease_protects_database_and_sqlite_wal_sidecars(tmp_path):
    state_directory = tmp_path / "private-state"
    database = state_directory / "jobs.sqlite3"
    adapter = WindowsSecureStorage()

    with adapter.protect_database(database) as lease:
        connection = sqlite3.connect(database)
        try:
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            assert mode.lower() == "wal"
            connection.execute("CREATE TABLE lease_probe (value TEXT)")
            connection.execute("INSERT INTO lease_probe VALUES ('protected')")
            lease.verify()
        finally:
            connection.close()
        lease.verify()

    assert database.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native ACL integration test")
def test_windows_lease_rejects_untrusted_sidecar_dacl(tmp_path):
    state_directory = tmp_path / "private-state"
    database = state_directory / "jobs.sqlite3"
    adapter = WindowsSecureStorage()

    with adapter.protect_database(database) as lease:
        database.touch()
        sidecar = Path(f"{database}-wal")
        sidecar.touch()
        try:
            _ctypes, _pywintypes, _win32api, _win32con, _win32file, win32security = (
                adapter._api()
            )
            # Replace the inherited ACL with an empty, protected DACL. A file
            # with this descriptor must not be accepted as a SQLite sidecar.
            handle = _win32file.CreateFile(
                str(sidecar),
                0x00040000 | 0x00020000,
                0x00000001 | 0x00000002,
                None,
                3,
                0x00200000,
                None,
            )
            try:
                empty_acl = win32security.ACL()
                win32security.SetSecurityInfo(
                    handle,
                    win32security.SE_FILE_OBJECT,
                    win32security.DACL_SECURITY_INFORMATION
                    | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                    None,
                    None,
                    empty_acl,
                    None,
                )
            finally:
                _win32file.CloseHandle(handle)

            # An empty protected DACL can deny READ_CONTROL itself, so the
            # adapter must fail closed when it cannot inspect the descriptor.
            with pytest.raises(
                PlatformStorageUnavailable, match="sidecar security could not be checked"
            ):
                lease.verify()
        finally:
            sidecar.unlink(missing_ok=True)



def test_windows_reparse_points_are_rejected_without_tag_allowlist(monkeypatch):
    class FakeFile:
        @staticmethod
        def GetFileInformationByHandle(_handle):
            return (WindowsSecureStorage._REPARSE,)

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_api",
        staticmethod(lambda: (None, None, None, None, FakeFile(), None)),
    )
    with pytest.raises(PlatformStorageUnavailable, match="unsupported reparse point"):
        WindowsSecureStorage._check_type(object(), True)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows drive type policy test")
def test_windows_adapter_rejects_mapped_network_drive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        WindowsSecureStorage,
        "_drive_type",
        classmethod(lambda _cls, _root: 4),  # DRIVE_REMOTE
    )
    with pytest.raises(PlatformStorageUnavailable, match="fixed local drive"):
        WindowsSecureStorage._require_fixed_local_drive(tmp_path / "jobs.sqlite3")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native ACL integration test")
def test_windows_adapter_does_not_rewrite_existing_directory_acl(tmp_path):
    state_directory = tmp_path / "private-state"
    state_directory.mkdir()
    database = state_directory / "jobs.sqlite3"
    adapter = WindowsSecureStorage()
    _ctypes, _pywintypes, _win32api, _win32con, win32file, win32security = (
        adapter._api()
    )

    handle = win32file.CreateFile(
        str(state_directory),
        0x00020000,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    try:
        before = win32security.GetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        before_owner = before.GetSecurityDescriptorOwner()
        before_acl = before.GetSecurityDescriptorDacl()
        before_aces = [
            before_acl.GetAce(index) for index in range(before_acl.GetAceCount())
        ]
    finally:
        win32file.CloseHandle(handle)

    with pytest.raises(PlatformStorageUnavailable), adapter.protect_database(database):
        pytest.fail("An existing non-dedicated directory must not be accepted.")

    handle = win32file.CreateFile(
        str(state_directory),
        0x00020000,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    try:
        after = win32security.GetSecurityInfo(
            handle,
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        after_acl = after.GetSecurityDescriptorDacl()
        after_aces = [
            after_acl.GetAce(index) for index in range(after_acl.GetAceCount())
        ]
        assert after.GetSecurityDescriptorOwner() == before_owner
        assert after_aces == before_aces
    finally:
        win32file.CloseHandle(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native SQLite persistence integration test")
def test_windows_job_store_persists_across_real_store_reopen(tmp_path):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    first = SQLiteJobStore(database, secure_storage=WindowsSecureStorage())
    created = first.create(
        owner_id="windows-owner",
        tool_id="software.install",
        action_digest="a" * 64,
        idempotency_key="windows-reopen-1",
    )

    # A distinct store instance must recover the committed record from the
    # same NTFS database after the first store has completed its operations.
    reopened = SQLiteJobStore(database, secure_storage=WindowsSecureStorage())
    recovered = reopened.get_for_owner(created["job_id"], "windows-owner")

    assert recovered["job_id"] == created["job_id"]
    assert recovered["state"] == created["state"] == "QUEUED"
    assert recovered["recent_events"][0]["message"] == "Job accepted into the local queue"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native concurrent SQLite integration test")
def test_windows_job_store_concurrent_instances_share_durable_database(tmp_path):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    first = SQLiteJobStore(database, secure_storage=WindowsSecureStorage())
    second = SQLiteJobStore(database, secure_storage=WindowsSecureStorage())

    def create_job(index: int):
        store = first if index % 2 == 0 else second
        return store.create(
            owner_id="windows-concurrent-owner",
            tool_id="software.install",
            action_digest=f"{index:064x}",
            idempotency_key=f"windows-concurrent-{index}",
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        created = list(executor.map(create_job, range(12)))

    assert len({job["job_id"] for job in created}) == 12
    recovered = first.list_for_owner("windows-concurrent-owner", limit=25)
    assert len(recovered) == 12
    assert {job["job_id"] for job in recovered} == {
        job["job_id"] for job in created
    }


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native handle-lifetime integration test")
def test_windows_lease_prevents_state_directory_rename_while_held(tmp_path):
    state_directory = tmp_path / "private-state"
    database = state_directory / "jobs.sqlite3"
    replacement = tmp_path / "replacement-state"
    adapter = WindowsSecureStorage()

    with adapter.protect_database(database):
        with pytest.raises(OSError):
            state_directory.rename(replacement)
        assert state_directory.is_dir()
        assert not replacement.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native handle-cleanup integration test")
def test_windows_lease_releases_directory_handles_after_verification_failure(
    tmp_path, monkeypatch
):
    state_directory = tmp_path / "private-state"
    database = state_directory / "jobs.sqlite3"
    replacement = tmp_path / "released-state"
    adapter = WindowsSecureStorage()

    def fail_directory_verification(_cls, _handle, _sid):
        raise PlatformStorageUnavailable("forced verification failure")

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_verify_directory",
        classmethod(fail_directory_verification),
    )

    with pytest.raises(
        PlatformStorageUnavailable, match="forced verification failure"
    ), adapter.protect_database(database):
        pytest.fail("The protection lease must fail before SQLite is opened.")

    # A successful rename proves the directory and parent handles were
    # released by ExitStack on the exception path.
    state_directory.rename(replacement)
    assert replacement.is_dir()

