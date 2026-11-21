from __future__ import annotations

import os

import pytest

from agent_backend import winget_execution


def test_winget_alias_path_uses_only_current_users_windows_apps(tmp_path):
    local_app_data = tmp_path / "LocalAppData"
    alias_directory = local_app_data / "Microsoft" / "WindowsApps"
    alias_directory.mkdir(parents=True)
    alias = alias_directory / "winget.exe"
    alias.write_bytes(b"test-alias")

    resolved = winget_execution._winget_alias_path(
        environ={"LOCALAPPDATA": str(local_app_data)}
    )

    assert resolved == alias
    assert resolved.name == "winget.exe"
    assert "WindowsApps" in resolved.parts


def test_winget_alias_path_fails_closed_when_alias_is_missing(tmp_path):
    with pytest.raises(winget_execution.WinGetExecutionError):
        winget_execution._winget_alias_path(
            environ={"LOCALAPPDATA": str(tmp_path)}
        )


def test_winget_alias_path_requires_local_app_data():
    with pytest.raises(winget_execution.WinGetExecutionError):
        winget_execution._winget_alias_path(environ={})


@pytest.mark.skipif(os.name == "nt", reason="non-Windows guard is tested only off Windows")
def test_real_execution_is_rejected_off_windows():
    with pytest.raises(
        winget_execution.WinGetExecutionError,
        match="available only on Windows",
    ):
        winget_execution.execute_approved_winget_install(None, None, work_root=None)
