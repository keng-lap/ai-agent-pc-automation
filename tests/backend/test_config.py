import pytest

from agent_backend.config import ConfigError, load_settings

ENV_NAMES = ["APP_ENV", "BACKEND_HOST", "BACKEND_PORT", "FRONTEND_PORT", "LOG_LEVEL"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_loopback_only():
    settings = load_settings(load_env_file=False)
    assert settings.backend_host == "127.0.0.1"
    assert settings.backend_port == 8000
    assert settings.frontend_port == 4200
    assert settings.app_env == "development"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com", ""])
def test_non_loopback_host_is_rejected(monkeypatch, host):
    monkeypatch.setenv("BACKEND_HOST", host)
    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_hosts_are_accepted(monkeypatch, host):
    monkeypatch.setenv("BACKEND_HOST", host)
    assert load_settings(load_env_file=False).backend_host == host


@pytest.mark.parametrize("value", ["abc", "0", "70000", "-1"])
def test_invalid_port_is_rejected(monkeypatch, value):
    monkeypatch.setenv("BACKEND_PORT", value)
    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)
