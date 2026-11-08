# F-516-01 local Google and Authenticator setup

This guide configures the already-approved local identity flow. It does not enable real PC execution.

## 1. Create a Google OAuth client

In Google Cloud Console:

1. Select/create a project and configure the OAuth consent screen.
2. Create an OAuth client ID of type **Web application**.
3. Add these exact authorized redirect URIs:
   - `http://127.0.0.1:8000/auth/google/callback` (the Agent login callback)
   - `http://127.0.0.1:8765/auth/google/callback` (one-time Master User subject bootstrap)
4. Keep the client ID and client secret private. Do not paste them into chat, Git, issues, or screenshots.

## 2. Configure local .env

Copy `.env.example` to `.env` if it does not already exist. Preserve the existing `LOCAL_AGENT_TOKEN` and Gemini settings. Fill only these Google values:

```dotenv
GOOGLE_OIDC_CLIENT_ID=your-client-id
GOOGLE_OIDC_CLIENT_SECRET=your-client-secret
GOOGLE_OIDC_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI=http://127.0.0.1:8765/auth/google/callback
MASTER_GOOGLE_SUB=
APP_SESSION_TTL_SECONDS=1800
AUTHENTICATOR_SECRET_PATH=
```

The value `1800` seconds (30 minutes) is a suggested initial session lifetime, not a hard-coded application default. Choose and set the value explicitly. Allowed range: 60–86400 seconds. An empty authenticator path uses the ignored local path `.agent-state/authenticator.json`.

## 3. Enroll the single Master User identity

From the repository root in PowerShell:

```powershell
python -m pip install -e .\src\backend
python .\scripts\bootstrap-master-user.py
```

The helper opens Google sign-in, receives the callback only on `127.0.0.1:8765`, verifies the Google ID token (signature, issuer, audience, nonce, verified email, and time claims), then prints the stable Google `sub` to the terminal. It does not write files or grant a session.

Confirm that the displayed Google account is the intended owner. Copy the stable `sub` value into `MASTER_GOOGLE_SUB` in `.env`. Never use an email address as the owner identifier.

## 4. Start and enroll the authenticator

Start the local app using the repository's normal Windows setup/launcher. Open the local web UI and choose **Login with Google**. After the Master User session is established:

1. Select **Set up authenticator**.
2. Scan the QR code with an RFC 6238 compatible app (Google Authenticator, Microsoft Authenticator, 2FAS, or Aegis).
3. Enter the six-digit code to confirm enrollment.
4. Store the authenticator device safely. The Agent intentionally has no SMS, email OTP, recovery code, second owner, or self-service lost-device replacement.

For a high-risk Dry Run approval, request a fresh challenge and enter a fresh six-digit code. The code is bound to that exact plan, digest, owner, and session and can be consumed only once. After restarting the backend, wait for the next 30-second authenticator code before approving; the current step is deliberately blocked to prevent replay from the previous process.

## 5. Security and support boundaries

- The backend remains loopback-only. Do not expose ports 8000/4200 or the callback listener to a LAN/public network.
- Google is contacted for OIDC identity only. Prompts, plans, files, and Windows telemetry are not sent to Google by this flow.
- Access/refresh tokens are discarded; the Agent keeps only its own opaque local session.
- Authenticator secret storage uses Windows DPAPI for the current Windows user.
- Sessions and step-up challenges are process-local and are invalidated on restart. Multi-worker mode is not supported.
- If the Google credentials or authenticator storage are missing or unavailable, high-risk approval fails closed.
- Lost-authenticator replacement is not implemented. Do not delete the DPAPI file to attempt recovery; use a separately approved trusted-setup procedure when one is defined.
- This implementation remains P1 Dry Run only. It does not authorize Phase 6 or any real Windows operation.
