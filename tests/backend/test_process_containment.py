import os

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
