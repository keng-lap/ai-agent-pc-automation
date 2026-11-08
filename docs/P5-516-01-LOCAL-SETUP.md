# F-516-01 local Google and Authenticator setup

This setup remains local-only and does not authorize real Windows actions or Phase 6.

## 1. Configure Google OAuth with the setup script

If this is a fresh checkout, run `.\scripts\setup.ps1` once to create `.env` and install dependencies. Then run:

```powershell
.\scripts\P516-01-setup-google-oauth.ps1
```

The script:

- Opens Google Cloud Console only when OAuth credentials need to be created or replaced.
- Requires one OAuth Client ID of type **Web application**.
- Shows the exact authorized redirect URIs required for the local backend and one-time Master User verification.
- Collects the Client Secret through a hidden prompt; never pass it as a command-line argument or paste it into chat, Git, issues, or screenshots.
- Preserves unrelated `.env` values, including `LOCAL_AGENT_TOKEN` and Gemini settings.
- Runs the existing Google OIDC bootstrap, verifies the selected Google account, and asks for explicit confirmation before setting/replacing the single Master User.
- Validates the complete local configuration before saving it. If Google verification fails or is cancelled, it does not save the OAuth settings.

If the Google OAuth consent screen is in **Testing** mode, add the intended Master User Gmail account to its test-user list. The script cannot create a Google Cloud project, consent screen, OAuth client, or client secret on the user's behalf.

After the script reports success, restart the local app:

```powershell
# Stop the current scripts\dev.ps1 window with Ctrl+C, then:
.\scripts\dev.ps1
```

Open `http://127.0.0.1:4200/` and choose **Login with Google**.

## 2. Enroll the authenticator

After the Master User session is established:

1. Select **Set up authenticator**.
2. Scan the QR code with an RFC 6238 compatible app (Google Authenticator, Microsoft Authenticator, 2FAS, or Aegis).
3. Enter the six-digit code to confirm enrollment.
4. Keep the authenticator device safe. The Agent intentionally has no SMS, email OTP, recovery code, second owner, or self-service lost-device replacement.

For a high-risk Dry Run approval, request a fresh challenge and enter a fresh six-digit code. The code is bound to that exact plan, digest, owner, and session and can be consumed only once. After restarting the backend, wait for the next 30-second authenticator code before approving; the current step is deliberately blocked to prevent replay from the previous process.

## 3. Security and support boundaries

- The backend remains loopback-only. Do not expose ports 8000/4200 or the callback listener to a LAN/public network.
- Google is contacted for OIDC identity only. Prompts, plans, files, and Windows telemetry are not sent to Google by this flow.
- Access/refresh tokens are discarded; the Agent keeps only its own opaque local session.
- Authenticator secret storage uses Windows DPAPI for the current Windows user.
- Sessions and step-up challenges are process-local and are invalidated on restart. Multi-worker mode is not supported.
- If Google credentials or authenticator storage are missing or unavailable, high-risk approval fails closed.
- Lost-authenticator replacement is not implemented. Do not delete the DPAPI file to attempt recovery; use a separately approved trusted-setup procedure when one is defined.
- This implementation remains P1 Dry Run only. It does not authorize Phase 6 or any real Windows operation.
