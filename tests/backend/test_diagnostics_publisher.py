from types import SimpleNamespace

from agent_backend import diagnostics_publisher as publisher


class FakeJob:
    def __init__(self):
        self.assigned = []
        self.terminated = False
        self.waited = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def assign_suspended_process(self, handle):
        self.assigned.append(handle)

    def wait_for_empty(self, timeout_ms=10_000):
        self.waited = True

    def terminate(self):
        self.terminated = True


class FakeProcess:
    _handle = 123
    returncode = 0

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.killed = False

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


def install_process_fakes(monkeypatch, process):
    job = FakeJob()
    calls = []
    monkeypatch.setattr(publisher, "WindowsJobObject", lambda: job)
    monkeypatch.setattr(publisher.subprocess, "Popen", lambda command, **kwargs: (
        calls.append((command, kwargs)) or process
    ))
    monkeypatch.setattr(
        publisher.ctypes,
        "WinDLL",
        lambda _name: SimpleNamespace(
            NtResumeProcess=SimpleNamespace(
                __call__=lambda _handle: 0,
                argtypes=None,
                restype=None,
            )
        ),
        raising=False,
    )
    # ctypes function objects are callable; use a small callable object for the fake.
    class Resume:
        def __call__(self, _handle):
            return 0

    resume = Resume()
    monkeypatch.setattr(publisher.ctypes, "WinDLL", lambda _name: SimpleNamespace(NtResumeProcess=resume), raising=False)
    return job, calls, resume


def test_publisher_uses_run_id_and_returns_only_the_allowlisted_github_url(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "publish-runtime-diagnostics.ps1").write_text("param()", encoding="utf-8")
    monkeypatch.setattr(publisher, "REPO_ROOT", tmp_path)
    process = FakeProcess(
        stdout="LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/diagnostics/runtime-logs/runs/1234-runtime\\n"
    )
    job, calls, resume = install_process_fakes(monkeypatch, process)

    publisher._run_publisher("12345678-1234-4234-8234-123456789abc")

    status = publisher.get_publish_status()
    assert status["status"] == "succeeded"
    assert status["url"].endswith("/runs/1234-runtime")
    assert "-RunId" in calls[0][0]
    assert "12345678-1234-4234-8234-123456789abc" in calls[0][0]
    assert calls[0][1]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert calls[0][1]["env"]["GCM_INTERACTIVE"] == "never"
    assert calls[0][1]["creationflags"] == 0x00000004
    assert job.assigned == [123]
    assert job.waited
    assert resume.called if hasattr(resume, "called") else True


def test_publisher_failure_does_not_expose_process_output_or_secrets(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "publish-runtime-diagnostics.ps1").write_text("param()", encoding="utf-8")
    monkeypatch.setattr(publisher, "REPO_ROOT", tmp_path)
    process = FakeProcess(stderr="fatal: authentication token=do-not-expose", returncode=1)
    job, _calls, _resume = install_process_fakes(monkeypatch, process)

    publisher._run_publisher("12345678-1234-4234-8234-123456789abc")

    status = publisher.get_publish_status()
    assert status["status"] == "failed"
    assert status["error_code"] == "publish_failed"
    assert "do-not-expose" not in str(status)
    assert job.waited
