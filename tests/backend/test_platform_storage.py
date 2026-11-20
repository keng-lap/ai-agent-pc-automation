import sqlite3
import stat
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_backend.job_store import JobStoreUnavailable, SQLiteJobStore
from agent_backend.platform_storage import (
    LinuxSecureStorage,
    PlatformStorageUnavailable,
    WindowsSecureStorage,
    _WindowsDatabaseProtectionLease,
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



@pytest.mark.skipif(sys.platform != "linux", reason="Linux pre-open sidecar validation test")
def test_linux_adapter_rejects_preexisting_sidecar_before_sqlite_connect(tmp_path, monkeypatch):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    database.parent.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.write_text("not a database")
    Path(f"{database}-journal").symlink_to(target)

    def unexpected_connect(*_args, **_kwargs):
        pytest.fail("SQLite must not open when a pre-existing sidecar is unsafe")

    monkeypatch.setattr("agent_backend.job_store.sqlite3.connect", unexpected_connect)
    with pytest.raises(JobStoreUnavailable, match="sidecar"):
        SQLiteJobStore(database, secure_storage=LinuxSecureStorage())




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
            # A protected Everyone ACE is readable but broader than the
            # explicit current-user-only ACL required for SQLite files.
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
                broad_acl = win32security.ACL()
                everyone = win32security.CreateWellKnownSid(
                    win32security.WinWorldSid, None
                )
                broad_acl.AddAccessAllowedAceEx(
                    win32security.ACL_REVISION, 0, 0x001F01FF, everyone
                )
                win32security.SetSecurityInfo(
                    handle,
                    win32security.SE_FILE_OBJECT,
                    win32security.DACL_SECURITY_INFORMATION
                    | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                    None,
                    None,
                    broad_acl,
                    None,
                )
            finally:
                _win32file.CloseHandle(handle)

            with pytest.raises(
                PlatformStorageUnavailable, match="explicit owner-only ACL"
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
    _ctypes, _pywintypes, _win32api, _win32con, win32file, _security = adapter._api()
    opened_handles = []
    closed_handles = []
    original_create = win32file.CreateFile
    original_close = win32file.CloseHandle
    original_final_open = WindowsSecureStorage._create_or_open_private_directory

    def track_create(*args, **kwargs):
        handle = original_create(*args, **kwargs)
        opened_handles.append(handle)
        return handle

    def track_close(handle):
        closed_handles.append(handle)
        return original_close(handle)

    def track_final_open(cls, *args, **kwargs):
        handle = original_final_open(*args, **kwargs)
        opened_handles.append(handle)
        return handle

    monkeypatch.setattr(win32file, "CreateFile", track_create)
    monkeypatch.setattr(win32file, "CloseHandle", track_close)
    monkeypatch.setattr(
        WindowsSecureStorage,
        "_create_or_open_private_directory",
        classmethod(track_final_open),
    )

    with pytest.raises(
        PlatformStorageUnavailable, match="forced verification failure"
    ), adapter.protect_database(database):
        pytest.fail("The protection lease must fail before SQLite is opened.")

    assert {int(handle) for handle in opened_handles} == {
        int(handle) for handle in closed_handles
    }
    # Keep the real namespace check separate: every retained directory handle
    # must be closed and the final directory must then be renameable.
    state_directory.rename(replacement)
    assert replacement.is_dir()




def test_windows_lease_never_changes_owner_of_untrusted_entry(monkeypatch):
    class FakeFile:
        @staticmethod
        def CreateFile(*_args, **_kwargs):
            return object()

        @staticmethod
        def GetFileInformationByHandle(_handle):
            return (0,)

        @staticmethod
        def CloseHandle(_handle):
            return None

    class FakeDescriptor:
        @staticmethod
        def GetSecurityDescriptorOwner():
            return "foreign-sid"

    class FakeSecurity:
        SE_FILE_OBJECT = 1
        OWNER_SECURITY_INFORMATION = 1
        DACL_SECURITY_INFORMATION = 4

        @staticmethod
        def GetSecurityInfo(_handle, _kind, _flags):
            return FakeDescriptor()

        @staticmethod
        def SetSecurityInfo(*_args, **_kwargs):
            pytest.fail("Verification must never repair an untrusted file owner")

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_api",
        staticmethod(lambda: (None, None, None, None, FakeFile(), FakeSecurity())),
    )
    lease = _WindowsDatabaseProtectionLease(Path("C:/private/jobs.sqlite3"), "current-sid")
    with pytest.raises(PlatformStorageUnavailable, match="owner SID"):
        lease.verify()


def test_windows_native_api_errors_are_recognized_for_translation():
    NativeError = type("error", (Exception,), {"__module__": "pywintypes"})
    assert WindowsSecureStorage._is_native_error(NativeError("failed"))



@pytest.mark.skipif(sys.platform != "win32", reason="Windows named-mutex integration test")
def test_windows_named_mutex_serializes_same_database_file_creation(
    tmp_path, monkeypatch
):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    first_created_database = threading.Event()
    continue_first_creation = threading.Event()
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_acquired = threading.Event()

    original_create_or_open = WindowsSecureStorage._create_or_open_private_file

    def pause_after_first_database_creation(cls, path, sid):
        original_create_or_open(path, sid)
        if path == database:
            first_created_database.set()
            assert continue_first_creation.wait(timeout=5)

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_create_or_open_private_file",
        classmethod(pause_after_first_database_creation),
    )

    def hold_first_lease():
        with WindowsSecureStorage().protect_database(database):
            first_acquired.set()
            assert release_first.wait(timeout=5)

    def acquire_second_lease():
        second_started.set()
        with WindowsSecureStorage().protect_database(database):
            second_acquired.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(hold_first_lease)
        assert first_created_database.wait(timeout=5)
        second = executor.submit(acquire_second_lease)
        try:
            assert second_started.wait(timeout=5)
            # Pause A after it created the main database but before it has
            # finished creating/verifying the complete SQLite file set.
            assert not second_acquired.wait(timeout=0.2)
        finally:
            continue_first_creation.set()
        assert first_acquired.wait(timeout=5)
        try:
            # B remains excluded while A holds the successful protection lease.
            assert not second_acquired.wait(timeout=0.2)
        finally:
            release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    assert second_acquired.is_set()



def test_windows_adapter_translates_native_api_error_to_store_error(
    tmp_path, monkeypatch
):
    NativeError = type("error", (Exception,), {"__module__": "pywintypes"})

    @contextmanager
    def fail_during_native_acquisition(_path):
        raise NativeError("native API failure")
        yield

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_protect_database",
        classmethod(lambda _cls, path: fail_during_native_acquisition(path)),
    )
    class TestLease:
        @staticmethod
        def verify():
            return None

    class TestStorage:
        @contextmanager
        def protect_database(self, database_path):
            database_path.parent.mkdir(parents=True, exist_ok=True)
            yield TestLease()

    store = SQLiteJobStore(
        tmp_path / "private-state" / "jobs.sqlite3",
        secure_storage=TestStorage(),
    )
    store._secure_storage = WindowsSecureStorage()

    with pytest.raises(
        JobStoreUnavailable, match="Windows security APIs failed"
    ), store._connection():
        pytest.fail("The native acquisition error must fail before SQLite opens.")



@pytest.mark.skipif(sys.platform != "win32", reason="Windows native wrong-owner fixture")
def test_windows_lease_rejects_wrong_owner_without_repair(tmp_path, monkeypatch):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    sidecar = Path(f"{database}-wal")
    adapter = WindowsSecureStorage()

    with adapter.protect_database(database) as lease:
        _ctypes, pywintypes, _api, _con, win32file, win32security = adapter._api()
        current_sid = adapter._sid()
        foreign_sid = win32security.CreateWellKnownSid(
            win32security.WinBuiltinAdministratorsSid, None
        )
        if foreign_sid == current_sid:
            pytest.skip("No distinct alternate owner SID is available")

        handle = win32file.CreateFile(
            str(sidecar),
            0x00080000 | 0x00020000,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            3,
            0x00200000,
            None,
        )
        try:
            try:
                win32security.SetSecurityInfo(
                    handle,
                    win32security.SE_FILE_OBJECT,
                    win32security.OWNER_SECURITY_INFORMATION,
                    foreign_sid,
                    None,
                    None,
                    None,
                )
            except pywintypes.error:
                pytest.skip("Runner cannot assign an alternate file owner")
        finally:
            win32file.CloseHandle(handle)

        original_set_security_info = win32security.SetSecurityInfo
        owner_mutations = []

        def record_owner_mutation(*args, **kwargs):
            owner_mutations.append(args)
            return original_set_security_info(*args, **kwargs)

        monkeypatch.setattr(win32security, "SetSecurityInfo", record_owner_mutation)
        with pytest.raises(PlatformStorageUnavailable, match="owner SID"):
            lease.verify()
        assert owner_mutations == []

        # Restore a safe fixture before the lease's final verification.
        restore = win32file.CreateFile(
            str(sidecar),
            0x00080000 | 0x00020000,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            3,
            0x00200000,
            None,
        )
        try:
            original_set_security_info(
                restore,
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
                current_sid,
                None,
                None,
                None,
            )
        finally:
            win32file.CloseHandle(restore)
        sidecar.unlink()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native reparse-point fixture")
@pytest.mark.parametrize("suffix", ["", "-wal"])
def test_windows_lease_rejects_database_or_sidecar_reparse_point(
    tmp_path, suffix
):
    database = tmp_path / "private-state" / "jobs.sqlite3"
    target = tmp_path / "outside-target.bin"
    target.write_bytes(b"outside")
    adapter = WindowsSecureStorage()

    with adapter.protect_database(database) as lease:
        entry = Path(f"{database}{suffix}")
        backup = entry.with_name(entry.name + ".original")
        entry.replace(backup)
        try:
            try:
                entry.symlink_to(target)
            except OSError:
                backup.replace(entry)
                pytest.skip("Runner does not permit creating a symbolic link")
            with pytest.raises(
                PlatformStorageUnavailable, match="unsupported reparse point"
            ):
                lease.verify()
        finally:
            entry.unlink(missing_ok=True)
            if backup.exists():
                backup.replace(entry)



@pytest.mark.skipif(sys.platform != "win32", reason="Windows native ancestor reparse-point fixture")
def test_windows_lease_rejects_reparse_point_ancestor(tmp_path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    try:
        linked_parent.symlink_to(real_parent, target_is_directory=True)
    except OSError:
        pytest.skip("Runner does not permit creating a directory symbolic link")

    database = linked_parent / "private-state" / "jobs.sqlite3"
    with pytest.raises(
        PlatformStorageUnavailable, match="unsupported reparse point"
    ), WindowsSecureStorage().protect_database(database):
        pytest.fail("A reparse-point ancestor must be rejected before SQLite opens.")



def test_windows_mutex_timeout_closes_handle_without_releasing(monkeypatch):
    class FakeFunction:
        def __init__(self, result):
            self.result = result
            self.calls = []

        def __call__(self, *args):
            self.calls.append(args)
            return self.result

    create_mutex = FakeFunction(1234)
    wait_for_single_object = FakeFunction(0x00000102)  # WAIT_TIMEOUT
    release_mutex = FakeFunction(1)
    close_handle = FakeFunction(1)
    kernel = SimpleNamespace(
        CreateMutexW=create_mutex,
        WaitForSingleObject=wait_for_single_object,
        ReleaseMutex=release_mutex,
        CloseHandle=close_handle,
    )
    fake_ctypes = SimpleNamespace(
        WinDLL=lambda *_args, **_kwargs: kernel,
        c_void_p=object,
        c_int=int,
        c_wchar_p=str,
        c_uint32=int,
    )

    class FakeSecurity:
        @staticmethod
        def ConvertSidToStringSid(_sid):
            return "S-1-5-21-123"

    monkeypatch.setattr(
        WindowsSecureStorage,
        "_api",
        staticmethod(lambda: (fake_ctypes, None, None, None, None, FakeSecurity())),
    )

    with pytest.raises(
        PlatformStorageUnavailable, match="mutex acquisition timed out"
    ), WindowsSecureStorage._database_mutex(
        Path("C:/private-state/jobs.sqlite3"), "current-user-sid"
    ):
        pytest.fail("The mutex timeout must fail before yielding the lease.")

    assert wait_for_single_object.calls[0][1] == 5_000
    assert close_handle.calls == [(1234,)]
    assert release_mutex.calls == []
