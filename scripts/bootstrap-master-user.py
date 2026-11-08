"""One-time local helper to obtain the verified Google OIDC subject for Master User setup.

This helper only prints the verified stable Google sub. It does not write .env,
create a session, enroll an authenticator, or change application permissions.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src" / "backend"))

from agent_backend.oidc import (  # noqa: E402
    GoogleOidcClient,
    OidcAuthenticationError,
    OidcTransactionStore,
)

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/auth/google/callback"
CALLBACK_TIMEOUT_SECONDS = 300


class CallbackHandler(BaseHTTPRequestHandler):
    oidc: GoogleOidcClient
    identity = None
    error = False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        host = self.headers.get("Host", "")
        if (
            host != "127.0.0.1:8765"
            or parsed.path != "/auth/google/callback"
            or parsed.fragment
        ):
            self._reply(400, "Invalid local callback.")
            return

        query = parse_qs(parsed.query, strict_parsing=True)
        state_values = query.get("state", [])
        code_values = query.get("code", [])
        if len(state_values) != 1 or len(code_values) != 1:
            self._reply(400, "Sign-in was not completed. Return to the terminal.")
            return

        try:
            type(self).identity = self.oidc.complete_login(
                state=state_values[0],
                code=code_values[0],
            )
        except OidcAuthenticationError:
            type(self).error = True
            self._reply(400, "Google identity verification failed. Return to the terminal.")
            return

        self._reply(200, "Google identity verified. Return to the terminal to finish setup.")

    def log_message(self, _format: str, *_args) -> None:
        # Never log callback query strings, authorization codes, or identity data.
        return

    def _reply(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>AI Agent Master User setup</title></head>"
            f"<body><h2>{message}</h2></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=False)
    client_id = os.environ.get("GOOGLE_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OIDC_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get(
        "GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI",
        DEFAULT_REDIRECT_URI,
    ).strip()

    if not client_id or not client_secret:
        print("Set GOOGLE_OIDC_CLIENT_ID and GOOGLE_OIDC_CLIENT_SECRET in local .env first.")
        return 2

    parsed = urlparse(redirect_uri)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 8765
        or parsed.path != "/auth/google/callback"
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        print("Bootstrap redirect URI must be http://127.0.0.1:8765/auth/google/callback.")
        return 2

    oidc = GoogleOidcClient(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        transaction_store=OidcTransactionStore(),
    )
    CallbackHandler.oidc = oidc
    CallbackHandler.identity = None
    CallbackHandler.error = False
    server = HTTPServer(("127.0.0.1", 8765), CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT_SECONDS

    login = oidc.begin_login()
    print("Opening Google sign-in in your browser...")
    if not webbrowser.open(login.authorization_url):
        print("Open this URL manually:")
        print(login.authorization_url)
    print("Waiting up to five minutes for the loopback callback.")
    try:
        server.handle_request()
    finally:
        server.server_close()

    identity = CallbackHandler.identity
    if CallbackHandler.error or identity is None:
        print("Master User subject was not obtained. No files were changed.")
        return 1

    print(f"Verified Google account: {identity.email}")
    print(f"Stable Google sub: {identity.sub}")
    print("Copy only the sub value into MASTER_GOOGLE_SUB in your local .env.")
    print("This helper did not save credentials or modify any project files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
