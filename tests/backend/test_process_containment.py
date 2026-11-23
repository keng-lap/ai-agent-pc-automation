import ctypes
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from agent_backend import process_containment as containment_module
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


def test_job_object_waits_until_active_process_count_reaches_zero():
    job = object.__new__(WindowsJobObject)
    job._handle = 1234
    active_counts = iter([2, 1, 0])
    calls = []

    def query(handle, info_class, buffer, buffer_size, returned_length):
        calls.append((handle, info_class, buffer_size, returned_length))
        accounting = ctypes.cast(
            buffer,
            ctypes.POINTER(containment_module._BasicAccountingInformation),
        ).contents
        accounting.ActiveProcesses = next(active_counts)
        return 1

    job._kernel32 = SimpleNamespace(QueryInformationJobObject=query)

    job.wait_for_empty(timeout_ms=1000)

    assert len(calls) == 3
    assert all(call[0] == 1234 and call[1] == 1 for call in calls)


def test_job_object_wait_times_out_while_processes_remain_active():
    job = object.__new__(WindowsJobObject)
    job._handle = 1234

    def query(_handle, _info_class, buffer, _buffer_size, _returned_length):
        accounting = ctypes.cast(
            buffer,
            ctypes.POINTER(containment_module._BasicAccountingInformation),
        ).contents
        accounting.ActiveProcesses = 1
        return 1

    job._kernel32 = SimpleNamespace(QueryInformationJobObject=query)

    with pytest.raises(ProcessContainmentError, match="Timed out waiting"):
        job.wait_for_empty(timeout_ms=1)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object APIs are required")
def test_terminating_job_waits_for_contained_parent_and_descendant(tmp_path):
    start_file = tmp_path / "start-child"
    child_ready_file = tmp_path / "child-ready"
    child_code = "import time; time.sleep(60)"
    parent_code = (
        "import os, subprocess, sys, time\n"
        f"start = {str(start_file)!r}\n"
        f"ready = {str(child_ready_file)!r}\n"
        "while not os.path.exists(start):\n"
        "    time.sleep(0.01)\n"
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        "open(ready, 'w', encoding='utf-8').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code])
    job = WindowsJobObject()
    try:
        job.assign_suspended_process(int(parent._handle))
        start_file.write_text("go", encoding="utf-8")
        deadline = time.monotonic() + 10
        while not child_ready_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert child_ready_file.exists(), "descendant process did not start"
        job.terminate()
        job.wait_for_empty(timeout_ms=10_000)
        assert parent.wait(timeout=5) is not None
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        job.close()

