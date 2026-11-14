"""Keep backend tests isolated from developer runtime settings."""

import os


# The app loads the repository .env when imported. Tests use fixed local
# settings so TestClient Host and Origin headers stay valid.
os.environ["BACKEND_HOST"] = "127.0.0.1"
os.environ["BACKEND_PORT"] = "8000"
os.environ["FRONTEND_PORT"] = "4200"
os.environ["LOCAL_AGENT_TOKEN"] = "a" * 64


# Route-level tests that exercise application behavior use an explicit synthetic
# principal. Auth-specific tests construct their own app and therefore still
# exercise the real fail-closed dependency and session validation.
from fastapi import Request

from agent_backend.auth_api import require_session
from agent_backend.main import app
from agent_backend.oidc import SessionPrincipal

def _synthetic_session(request: Request) -> SessionPrincipal:
    principal = SessionPrincipal(
        owner_sub="synthetic-test-owner",
        session_id="synthetic-test-session",
    )
    # Some route handlers bind step-up state to request.state.principal in
    # addition to consuming the dependency result.
    request.state.principal = principal
    return principal


# The shared route-test app must stay authentication-disabled regardless of a
# developer's local .env. Auth-specific tests build their own configured app.
app.state.auth_services = None
app.dependency_overrides[require_session] = _synthetic_session
