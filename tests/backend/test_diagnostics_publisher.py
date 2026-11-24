from types import SimpleNamespace

from agent_backend import diagnostics_publisher as publisher


def test_publisher_uses_run_id_and_returns_only_the_allowlisted_github_url(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "publish-runtime-diagnostics.ps1").write_text("param()", encoding="utf-8")
    monkeypatch.setattr(publisher, "REPO_ROOT", tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/diagnostics/runtime-logs/runs/1234-runtime\n",
            stderr="",
        )

    monkeypatch.setattr(publisher.subprocess, "run", fake_run)
    publisher._run_publisher("12345678-1234-4234-8234-123456789abc")

    status = publisher.get_publish_status()
    assert status["status"] == "succeeded"
    assert status["url"].endswith("/runs/1234-runtime")
    assert "-RunId" in calls[0][0]
    assert "12345678-1234-4234-8234-123456789abc" in calls[0][0]
    assert calls[0][1]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert calls[0][1]["env"]["GCM_INTERACTIVE"] == "never"


def test_publisher_failure_does_not_expose_process_output_or_secrets(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "publish-runtime-diagnostics.ps1").write_text("param()", encoding="utf-8")
    monkeypatch.setattr(publisher, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="fatal: authentication token=do-not-expose",
        ),
    )

    publisher._run_publisher("12345678-1234-4234-8234-123456789abc")

    status = publisher.get_publish_status()
    assert status["status"] == "failed"
    assert status["error_code"] == "publish_failed"
    assert "do-not-expose" not in str(status)
