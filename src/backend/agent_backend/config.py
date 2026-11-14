"""Environment-based configuration.

Values come from the process environment, optionally loaded from the
repository-root `.env` file (never committed; see `.env.example`).

Security (approved proposal P-SEC-1, Phase 1): the backend only binds to a
loopback address. Any other host is rejected at startup.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOCAL_AGENT_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# src/backend/agent_backend/config.py -> repository root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(ValueError):
    """Raised when configuration is invalid or unsafe."""


def validate_authenticator_secret_path(path: Path) -> Path:
    """Require the secret file to live in the app-owned authenticator directory."""
    if not isinstance(path, Path):
        raise ConfigError("AUTHENTICATOR_SECRET_PATH must be a filesystem path.")
    expected_dir = Path(os.path.abspath(REPO_ROOT / ".agent-state" / "authenticator"))
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    if candidate.parent != expected_dir:
        raise ConfigError(
            "AUTHENTICATOR_SECRET_PATH must be a direct child of the "
            "dedicated .agent-state/authenticator directory."
        )
    return candidate


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    frontend_port: int
    log_level: str
    local_agent_token: str
    google_oidc_client_id: str | None = None
    google_oidc_client_secret: str | None = None
    google_oidc_redirect_uri: str | None = None
    master_google_sub: str | None = None
    app_session_ttl_seconds: int | None = None
    authenticator_secret_path: Path | None = None
    job_store_path: Path | None = None

    @property
    def auth_enabled(self) -> bool:
        return all(
            value is not None
            for value in (
                self.google_oidc_client_id,
                self.google_oidc_client_secret,
                self.google_oidc_redirect_uri,
                self.master_google_sub,
                self.app_session_ttl_seconds,
                self.authenticator_secret_path,
            )
        )


def _port(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not 1 <= value <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535, got {value}")
    return value


def load_settings(*, load_env_file: bool = True) -> Settings:
    if load_env_file:
        # Real environment variables win over values in .env.
        load_dotenv(REPO_ROOT / ".env", override=False)

    host = os.environ.get("BACKEND_HOST", "127.0.0.1").strip()
    if host not in LOOPBACK_HOSTS:
        raise ConfigError(
            f"BACKEND_HOST={host!r} is not a loopback address. "
            "The backend must bind to 127.0.0.1 only (see docs/PROPOSALS.md, P-SEC-1). "
            "Changing this requires project owner approval."
        )

    token = os.environ.get("LOCAL_AGENT_TOKEN", "")
    if not LOCAL_AGENT_TOKEN_PATTERN.fullmatch(token):
        raise ConfigError(
            "LOCAL_AGENT_TOKEN must be a 64-character lowercase hexadecimal secret. "
            "Run scripts\\setup.ps1 to generate it."
        )

    backend_port = _port("BACKEND_PORT", 8000)
    frontend_port = _port("FRONTEND_PORT", 4200)

    auth_env_names = (
        "GOOGLE_OIDC_CLIENT_ID",
        "GOOGLE_OIDC_CLIENT_SECRET",
        "MASTER_GOOGLE_SUB",
        "APP_SESSION_TTL_SECONDS",
        "GOOGLE_OIDC_REDIRECT_URI",
        "AUTHENTICATOR_SECRET_PATH",
    )
    auth_values = {name: os.environ.get(name, "").strip() for name in auth_env_names}
    auth_configured = any(auth_values.values())
    auth_settings: dict[str, object] = {}
    if auth_configured:
        required_names = (
            "GOOGLE_OIDC_CLIENT_ID",
            "GOOGLE_OIDC_CLIENT_SECRET",
            "MASTER_GOOGLE_SUB",
            "APP_SESSION_TTL_SECONDS",
        )
        missing = [name for name in required_names if not auth_values[name]]
        if missing:
            raise ConfigError(
                "Google authentication configuration is incomplete: "
                + ", ".join(missing)
            )
        client_id = auth_values["GOOGLE_OIDC_CLIENT_ID"]
        client_secret = auth_values["GOOGLE_OIDC_CLIENT_SECRET"]
        master_sub = auth_values["MASTER_GOOGLE_SUB"]
        if len(client_id) > 512 or len(client_secret) > 512 or len(master_sub) > 256:
            raise ConfigError("Google authentication configuration exceeds its size limit.")
        try:
            session_ttl = int(auth_values["APP_SESSION_TTL_SECONDS"])
        except ValueError:
            raise ConfigError("APP_SESSION_TTL_SECONDS must be an integer.") from None
        if not 60 <= session_ttl <= 86400:
            raise ConfigError("APP_SESSION_TTL_SECONDS must be between 60 and 86400.")
        redirect_uri = auth_values["GOOGLE_OIDC_REDIRECT_URI"] or (
            f"http://127.0.0.1:{backend_port}/auth/google/callback"
        )
        parsed_redirect = urlparse(redirect_uri)
        if (
            parsed_redirect.scheme != "http"
            or parsed_redirect.hostname not in {"127.0.0.1", "localhost"}
            or parsed_redirect.port != backend_port
            or parsed_redirect.path != "/auth/google/callback"
            or parsed_redirect.query
            or parsed_redirect.fragment
            or parsed_redirect.username is not None
            or parsed_redirect.password is not None
        ):
            raise ConfigError(
                "GOOGLE_OIDC_REDIRECT_URI must be the configured loopback callback URL."
            )
        authenticator_state_dir = Path(
            os.path.abspath(REPO_ROOT / ".agent-state" / "authenticator")
        )
        secret_path = validate_authenticator_secret_path(
            Path(
                auth_values["AUTHENTICATOR_SECRET_PATH"]
                or (authenticator_state_dir / "authenticator.json")
            ).expanduser()
        )
        auth_settings = {
            "google_oidc_client_id": client_id,
            "google_oidc_client_secret": client_secret,
            "google_oidc_redirect_uri": redirect_uri,
            "master_google_sub": master_sub,
            "app_session_ttl_seconds": session_ttl,
            "authenticator_secret_path": secret_path,
        }

    return Settings(
        app_env=os.environ.get("APP_ENV", "development").strip(),
        backend_host=host,
        backend_port=backend_port,
        frontend_port=frontend_port,
        log_level=os.environ.get("LOG_LEVEL", "info").strip().lower(),
        local_agent_token=token,
        job_store_path=Path(os.environ.get("JOB_STORE_PATH", str(REPO_ROOT / ".agent-state" / "jobs.sqlite3"))).expanduser(),
        **auth_settings,
    )
