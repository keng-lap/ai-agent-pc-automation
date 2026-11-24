import os

import pytest

from agent_backend import runtime_privilege


def test_non_windows_process_is_not_treated_as_windows_elevated(monkeypatch):
    monkeypatch.setattr(runtime_privilege.os, "name", "posix")
    assert runtime_privilege.is_current_process_elevated() is False


def test_backend_startup_rejects_elevated_process(monkeypatch):
    monkeypatch.setattr(runtime_privilege, "is_current_process_elevated", lambda: True)

    with pytest.raises(
        runtime_privilege.BackendPrivilegeError,
        match="Backend/Agent must run unelevated",
    ):
        runtime_privilege.enforce_backend_not_elevated()


def test_backend_startup_allows_non_elevated_process(monkeypatch):
    monkeypatch.setattr(runtime_privilege, "is_current_process_elevated", lambda: False)

    runtime_privilege.enforce_backend_not_elevated()


def test_backend_startup_fails_closed_when_token_cannot_be_verified(monkeypatch):
    def fail_token_query():
        raise runtime_privilege.BackendPrivilegeError("token query failed")

    monkeypatch.setattr(runtime_privilege, "is_current_process_elevated", fail_token_query)

    with pytest.raises(runtime_privilege.BackendPrivilegeError, match="token query failed"):
        runtime_privilege.enforce_backend_not_elevated()


@pytest.mark.skipif(os.name != "nt", reason="Windows process token APIs are required")
def test_windows_backend_process_token_is_not_elevated():
    assert runtime_privilege.is_current_process_elevated() is False
