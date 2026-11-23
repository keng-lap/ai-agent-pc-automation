import os
from types import SimpleNamespace

import pytest

from agent_backend.process_containment import ProcessContainmentError, WindowsJobObject


def test_windows_job_object_is_explicitly_unavailable_off_windows():
    if os.name == "nt":
        pytest.skip("this assertion applies only to non-Windows hosts")
    with pytest.raises(ProcessContainmentError, match="only on Windows"):
        WindowsJobObject()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object APIs are required")
def test_windows_job_object_creates_and_closes_with_kill_on_close_policy():
    with WindowsJobObject() as job:
        assert job.is_open
        with pytest.raises(ValueError, match="native process handle"):
            job.assign_suspended_process(0)
    assert not job.is_open


def test_job_object_waits_for_all_contained_processes():
    job = object.__new__(WindowsJobObject)
    job._handle = 1234
    calls = []
    def wait(handle, timeout):
        calls.append((handle, timeout))
        return 0

    job._kernel32 = SimpleNamespace(WaitForSingleObject=wait)

    job.wait_for_empty()

    assert calls == [(1234, 0xFFFFFFFF)]


def test_job_object_wait_fails_closed_when_process_tree_does_not_exit():
    job = object.__new__(WindowsJobObject)
    job._handle = 1234
    def wait(_handle, _timeout):
        return 0x00000102

    job._kernel32 = SimpleNamespace(WaitForSingleObject=wait)

    with pytest.raises(ProcessContainmentError, match="Timed out waiting"):
        job.wait_for_empty(timeout_ms=10)
