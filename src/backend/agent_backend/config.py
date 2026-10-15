"""Environment-based configuration.

Values come from the process environment, optionally loaded from the
repository-root `.env` file (never committed; see `.env.example`).

Security (approved proposal P-SEC-1, Phase 1): the backend only binds to a
loopback address. Any other host is rejected at startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# src/backend/agent_backend/config.py -> repository root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(ValueError):
    """Raised when configuration is invalid or unsafe."""


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    frontend_port: int
    log_level: str


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

    return Settings(
        app_env=os.environ.get("APP_ENV", "development").strip(),
        backend_host=host,
        backend_port=_port("BACKEND_PORT", 8000),
        frontend_port=_port("FRONTEND_PORT", 4200),
        log_level=os.environ.get("LOG_LEVEL", "info").strip().lower(),
    )
