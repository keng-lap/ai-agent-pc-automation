import pytest
from pydantic import ValidationError

from agent_backend import winget_adapter


def _request(**overrides):
    values = {
        "package_id": "DBeaver.DBeaver.Community",
        "version": "25.3.4",
        "architecture": "x64",
        "scope": "user",
        "source": "winget",
        "evidence_sha256": "a" * 64,
    }
    values.update(overrides)
    return winget_adapter.VerifiedInstallRequest.model_validate(values)


def _install_alias(tmp_path, monkeypatch):
    root = tmp_path / "LocalAppData"
    alias = root / "Microsoft" / "WindowsApps" / "winget.exe"
    alias.parent.mkdir(parents=True)
    alias.write_bytes(b"test placeholder")
    monkeypatch.setenv("LOCALAPPDATA", str(root))
    return alias


def test_request_rejects_arbitrary_or_unbounded_package_values():
    with pytest.raises(ValidationError):
        _request(package_id="DBeaver.DBeaver.Community && whoami")
    with pytest.raises(ValidationError):
        _request(version="latest; arbitrary")
    with pytest.raises(ValidationError):
        _request(scope="machine")
    with pytest.raises(ValidationError):
        _request(source="chocolatey")
    with pytest.raises(ValidationError):
        _request(evidence_sha256="not-a-digest")


def test_arguments_are_fixed_and_user_scoped():
    args = winget_adapter.build_install_arguments(_request())

    assert args == (
        "install",
        "--id",
        "DBeaver.DBeaver.Community",
        "--exact",
        "--version",
        "25.3.4",
        "--architecture",
        "x64",
        "--scope",
        "user",
        "--source",
        "winget",
        "--silent",
        "--disable-interactivity",
        "--accept-package-agreements",
        "--accept-source-agreements",
    )
    assert "shell" not in args
    assert "--override" not in args
    assert "--force" not in args


def test_execution_uses_fixed_alias_and_shell_false(tmp_path, monkeypatch):
    alias = _install_alias(tmp_path, monkeypatch)
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return winget_adapter.subprocess.CompletedProcess(command, 0, "installed", "")

    result = winget_adapter.install_verified_package(_request(), runner=runner)

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.output_excerpt == "installed"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == str(alias)
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["timeout"] == winget_adapter.INSTALL_TIMEOUT_SECONDS
    assert kwargs["stdin"] is winget_adapter.subprocess.DEVNULL


def test_missing_fixed_alias_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("runner must not be called")

    with pytest.raises(RuntimeError, match="winget_unavailable"):
        winget_adapter.install_verified_package(_request(), runner=runner)

    assert calls == []


def test_timeout_is_reported_without_claiming_success(tmp_path, monkeypatch):
    _install_alias(tmp_path, monkeypatch)

    def runner(*args, **kwargs):
        raise winget_adapter.subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="still running")

    result = winget_adapter.install_verified_package(_request(), runner=runner)

    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.output_excerpt == "still running"


def test_process_output_is_bounded(tmp_path, monkeypatch):
    _install_alias(tmp_path, monkeypatch)

    def runner(command, **kwargs):
        return winget_adapter.subprocess.CompletedProcess(command, 1603, "x" * 9000, "")

    result = winget_adapter.install_verified_package(_request(), runner=runner)

    assert result.exit_code == 1603
    assert len(result.output_excerpt) == winget_adapter.MAX_OUTPUT_CHARS
