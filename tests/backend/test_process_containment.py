import multiprocessing
import os
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
        accounting = containment_module.ctypes.cast(
            buffer,
            containment_module.ctypes.POINTER(
                containment_module._BasicAccountingInformation,
            ),
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
        accounting = containment_module.ctypes.cast(
            buffer,
            containment_module.ctypes.POINTER(containment_module._BasicAccountingInformation),
        ).contents
        accounting.ActiveProcesses = 1
        return 1

    job._kernel32 = SimpleNamespace(QueryInformationJobObject=query)

    with pytest.raises(ProcessContainmentError, match="Timed out waiting"):
        job.wait_for_empty(timeout_ms=1)


def _sleep_for_process_tree():
    time.sleep(60)


def _spawn_contained_descendant(start_event, child_ready_event):
    if not start_event.wait(timeout=10):
        return
    child = multiprocessing.get_context("spawn").Process(target=_sleep_for_process_tree)
    child.start()
    child_ready_event.set()
    child.join()
    time.sleep(60)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object APIs are required")
def test_terminating_job_waits_for_contained_parent_and_descendant():
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    child_ready_event = context.Event()
    parent = context.Process(
        target=_spawn_contained_descendant,
        args=(start_event, child_ready_event),
    )
    parent.start()
    job = WindowsJobObject()
    try:
        job.assign_suspended_process(int(parent.sentinel))
        start_event.set()
        assert child_ready_event.wait(timeout=10), "descendant process did not start"
        job.terminate()
        job.wait_for_empty(timeout_ms=10_000)
        parent.join(timeout=5)
        assert not parent.is_alive()
    finally:
        if parent.is_alive():
            parent.terminate()
            parent.join(timeout=5)
        job.close()
