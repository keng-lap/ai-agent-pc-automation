import pytest

from agent_backend.config import (
    REPO_ROOT,
    ConfigError,
    default_state_directory,
    load_settings,
    real_install_release_authorization_from_env,
)

ENV_NAMES = [
    "APP_ENV",
    "BACKEND_HOST",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "LOG_LEVEL",
    "GOOGLE_OIDC_CLIENT_ID",
    "GOOGLE_OIDC_CLIENT_SECRET",
    "MASTER_GOOGLE_SUB",
    "APP_SESSION_TTL_SECONDS",
    "GOOGLE_OIDC_REDIRECT_URI",
    "AUTHENTICATOR_SECRET_PATH",
    "JOB_STORE_PATH",
    "LOCALAPPDATA",
    "AI_AGENT_ENABLE_REAL_INSTALL",
    "AI_AGENT_REAL_INSTALL_RELEASE_TASK",
    "AI_AGENT_REAL_INSTALL_PACKAGE_ID",
    "AI_AGENT_REAL_INSTALL_VERSION",
    "AI_AGENT_REAL_INSTALL_EXPIRES_AT",
    "AI_AGENT_REAL_INSTALL_NONCE",
]


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
    assert settings.job_store_path == REPO_ROOT / ".agent-state-Jobs" / "jobs.sqlite3"


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



def test_google_auth_configuration_is_disabled_when_no_auth_values_are_set():
    settings = load_settings(load_env_file=False)
    assert settings.auth_enabled is False


def test_google_auth_configuration_requires_all_identity_fields(monkeypatch):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")

    with pytest.raises(ConfigError, match="incomplete"):
        load_settings(load_env_file=False)


def test_google_auth_configuration_accepts_complete_loopback_setup(monkeypatch):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MASTER_GOOGLE_SUB", "stable-google-sub")
    monkeypatch.setenv("APP_SESSION_TTL_SECONDS", "1800")

    settings = load_settings(load_env_file=False)

    assert settings.auth_enabled is True
    assert settings.google_oidc_redirect_uri == "http://127.0.0.1:8000/auth/google/callback"
    assert settings.app_session_ttl_seconds == 1800
    assert settings.authenticator_secret_path.name == "authenticator.json"
    assert settings.authenticator_secret_path.parent == default_state_directory() / "authenticator"


@pytest.mark.parametrize("ttl", ["0", "59", "86401", "invalid"])
def test_google_auth_configuration_rejects_invalid_session_ttl(monkeypatch, ttl):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MASTER_GOOGLE_SUB", "stable-google-sub")
    monkeypatch.setenv("APP_SESSION_TTL_SECONDS", ttl)

    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://127.0.0.1:8000/auth/google/callback",
        "http://0.0.0.0:8000/auth/google/callback",
        "http://127.0.0.1:9000/auth/google/callback",
        "http://127.0.0.1:8000/other",
    ],
)
def test_google_auth_configuration_rejects_non_loopback_redirect(monkeypatch, redirect_uri):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MASTER_GOOGLE_SUB", "stable-google-sub")
    monkeypatch.setenv("APP_SESSION_TTL_SECONDS", "1800")
    monkeypatch.setenv("GOOGLE_OIDC_REDIRECT_URI", redirect_uri)

    with pytest.raises(ConfigError):
        load_settings(load_env_file=False)



def test_windows_user_state_defaults_to_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert default_state_directory() == tmp_path / "Local" / "AI-Agent-PC-Automation"
    settings = load_settings(load_env_file=False)
    assert settings.job_store_path == default_state_directory().with_name(default_state_directory().name + "-Jobs") / "jobs.sqlite3"


def test_explicit_job_store_path_override_is_preserved(monkeypatch, tmp_path):
    custom_path = tmp_path / "custom" / "jobs.sqlite3"
    monkeypatch.setenv("JOB_STORE_PATH", str(custom_path))

    settings = load_settings(load_env_file=False)

    assert settings.job_store_path == custom_path

def test_two_windows_profiles_resolve_to_separate_state_roots(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "LOCALAPPDATA",
        str(tmp_path / "profile-a" / "AppData" / "Local"),
    )
    profile_a = default_state_directory()

    monkeypatch.setenv(
        "LOCALAPPDATA",
        str(tmp_path / "profile-b" / "AppData" / "Local"),
    )
    profile_b = default_state_directory()

    assert profile_a != profile_b
    assert profile_a.name == "AI-Agent-PC-Automation"
    assert profile_b.name == "AI-Agent-PC-Automation"


def test_google_auth_configuration_rejects_secret_path_outside_dedicated_state_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MASTER_GOOGLE_SUB", "stable-google-sub")
    monkeypatch.setenv("APP_SESSION_TTL_SECONDS", "1800")
    monkeypatch.setenv(
        "AUTHENTICATOR_SECRET_PATH",
        str(tmp_path / "shared" / "authenticator.json"),
    )

    with pytest.raises(ConfigError, match="per-user authenticator state directory"):
        load_settings(load_env_file=False)


def test_real_install_is_disabled_by_default():
    settings = load_settings(load_env_file=False)
    assert settings.real_install_enabled is False


@pytest.mark.parametrize("value", ["true", "yes", "2", "enabled", ""])
def test_real_install_flag_rejects_ambiguous_values(monkeypatch, value):
    monkeypatch.setenv("AI_AGENT_ENABLE_REAL_INSTALL", value)
    with pytest.raises(ConfigError, match="AI_AGENT_ENABLE_REAL_INSTALL"):
        load_settings(load_env_file=False)


def test_real_install_requires_exact_bounded_one_use_release(monkeypatch):
    from datetime import UTC, datetime, timedelta

    monkeypatch.setenv("AI_AGENT_ENABLE_REAL_INSTALL", "1")
    monkeypatch.setenv("AI_AGENT_REAL_INSTALL_RELEASE_TASK", "P6-609-C")
    monkeypatch.setenv("AI_AGENT_REAL_INSTALL_PACKAGE_ID", "Contoso.Editor")
    monkeypatch.setenv("AI_AGENT_REAL_INSTALL_VERSION", "2.4.1")
    monkeypatch.setenv("AI_AGENT_REAL_INSTALL_EXPIRES_AT", (datetime.now(UTC) + timedelta(minutes=5)).isoformat())
    monkeypatch.setenv("AI_AGENT_REAL_INSTALL_NONCE", "a" * 64)
    settings = load_settings(load_env_file=False)
    assert settings.real_install_enabled is True
    assert settings.real_install_release_authorization.package_id == "Contoso.Editor"


@pytest.mark.parametrize(
    "missing_name",
    [
        "AI_AGENT_REAL_INSTALL_RELEASE_TASK",
        "AI_AGENT_REAL_INSTALL_PACKAGE_ID",
        "AI_AGENT_REAL_INSTALL_VERSION",
        "AI_AGENT_REAL_INSTALL_EXPIRES_AT",
        "AI_AGENT_REAL_INSTALL_NONCE",
    ],
)
def test_real_install_release_rejects_each_missing_required_value(missing_name):
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    environ = {
        "AI_AGENT_ENABLE_REAL_INSTALL": "1",
        "AI_AGENT_REAL_INSTALL_RELEASE_TASK": "P6-609-C",
        "AI_AGENT_REAL_INSTALL_PACKAGE_ID": "Contoso.Editor",
        "AI_AGENT_REAL_INSTALL_VERSION": "2.4.1",
        "AI_AGENT_REAL_INSTALL_EXPIRES_AT": (now + timedelta(minutes=5)).isoformat(),
        "AI_AGENT_REAL_INSTALL_NONCE": "a" * 64,
    }
    del environ[missing_name]

    with pytest.raises(ConfigError):
        real_install_release_authorization_from_env(environ=environ, now=now)


@pytest.mark.parametrize(
    "changes",
    [
        {"AI_AGENT_REAL_INSTALL_RELEASE_TASK": "P6-OTHER"},
        {"AI_AGENT_REAL_INSTALL_NONCE": "not-a-valid-nonce"},
        {"AI_AGENT_REAL_INSTALL_EXPIRES_AT": "2026-11-23T12:05:00"},
        {"AI_AGENT_REAL_INSTALL_EXPIRES_AT": "2026-11-23T12:00:00+00:00"},
        {"AI_AGENT_REAL_INSTALL_EXPIRES_AT": "2026-11-23T12:15:01+00:00"},
    ],
)
def test_real_install_release_rejects_invalid_task_nonce_and_expiry(changes):
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    environ = {
        "AI_AGENT_ENABLE_REAL_INSTALL": "1",
        "AI_AGENT_REAL_INSTALL_RELEASE_TASK": "P6-609-C",
        "AI_AGENT_REAL_INSTALL_PACKAGE_ID": "Contoso.Editor",
        "AI_AGENT_REAL_INSTALL_VERSION": "2.4.1",
        "AI_AGENT_REAL_INSTALL_EXPIRES_AT": (now + timedelta(minutes=5)).isoformat(),
        "AI_AGENT_REAL_INSTALL_NONCE": "a" * 64,
    }
    environ.update(changes)

    with pytest.raises(ConfigError):
        real_install_release_authorization_from_env(environ=environ, now=now)


def test_real_install_release_accepts_exact_fifteen_minute_expiry():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    environ = {
        "AI_AGENT_ENABLE_REAL_INSTALL": "1",
        "AI_AGENT_REAL_INSTALL_RELEASE_TASK": "P6-609-C",
        "AI_AGENT_REAL_INSTALL_PACKAGE_ID": "Contoso.Editor",
        "AI_AGENT_REAL_INSTALL_VERSION": "2.4.1",
        "AI_AGENT_REAL_INSTALL_EXPIRES_AT": (now + timedelta(minutes=15)).isoformat(),
        "AI_AGENT_REAL_INSTALL_NONCE": "a" * 64,
    }

    authorization = real_install_release_authorization_from_env(environ=environ, now=now)

    assert authorization is not None
    assert authorization.expires_at == now + timedelta(minutes=15)
