import stat

import pytest

from agent_backend.platform_storage import (
    LinuxSecureStorage,
    PlatformStorageUnavailable,
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


def test_linux_adapter_creates_private_state_directory_and_database(tmp_path):
    adapter = LinuxSecureStorage()
    database = tmp_path / "private-state" / "jobs.sqlite3"

    adapter.prepare_database_path(database)
    database.touch()
    adapter.finalize_database_file(database)

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_linux_adapter_rejects_symlink_database_path(tmp_path):
    adapter = LinuxSecureStorage()
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "private-state" / "jobs.sqlite3"
    link.parent.mkdir()
    link.symlink_to(target)

    with pytest.raises(PlatformStorageUnavailable, match="symbolic link"):
        adapter.prepare_database_path(link)
