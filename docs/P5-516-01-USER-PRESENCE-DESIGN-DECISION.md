# P5-516-01 — User-Presence and Step-Up Verification Decision

## Decision record

| Field | Value |
|---|---|
| Decision ID | D-P5-516-01 |
| Finding | F-516-01 — P1 approval does not prove human presence |
| Status | **Approved direction; TOTP replaces SMS by Product Owner decision on 2026-11-08** |
| Decision owner | Product Owner |
| Decision date | 2026-11-08 |
| Scope | Identity sign-in and step-up confirmation for a future exact-action approval flow |
| Change type | Documentation only |

## 1. Context and approved direction

The current local API token, Origin header, plan ID, and approval request do not prove that the owner personally intended to approve an action.

The Product Owner has approved:
1. Sign in using **Sign in with Google** through Google OpenID Connect (OIDC).
2. For a high-risk action, require a second confirmation using a **TOTP code from an authenticator app**, enrolled by scanning a one-time QR code during trusted setup.
3. Ordinary, non-high-risk interactions may use the authenticated application session, subject to existing policy and permission gates.
4. Exactly one Master User owns the installation. No second Master User, self-promotion, recovery codes, or parallel admin recovery account.
5. Google Account recovery remains entirely Google's responsibility. The AI Agent must not build a duplicate Google Account recovery flow or send Gmail recovery OTPs.

The Product Owner explicitly rejected paid SMS delivery. TOTP is generated and verified locally; no SMS, messaging provider, or authenticator-vendor API is needed. This decision does not approve a real machine-changing capability.

## 2. Approved decisions

### D1 — Google sign-in and single Master User

Use Google OIDC for application sign-in. Identify the owner by the stable Google `sub` after validating the identity response. Email may be displayed as an account attribute but is not the durable identity key.

Only the one Google identity explicitly enrolled as Master User during trusted setup may access owner functions. Do not auto-enroll the first account that signs in.

### D2 — Authenticator-app TOTP step-up

For every future high-risk approval, require a fresh TOTP code from the enrolled authenticator app. Enroll it during trusted setup by displaying a one-time QR code using the standard `otpauth://` provisioning format.

Support standards-compatible apps such as Google Authenticator, Microsoft Authenticator, 2FAS, and Aegis. These apps do not need to connect to the AI Agent or provide an API.

A successful Google sign-in is not action approval. A successful TOTP verification is not blanket approval; it must be bound to the exact action being approved.

### D3 — Exact-action binding

The TOTP challenge must be bound server-side to:
- authenticated Master User identity;
- authenticated application session;
- immutable action/plan identifier and canonical action digest;
- server-derived risk classification;
- challenge identifier and expiry.

Any material change to the action or its parameters invalidates the challenge and requires a new review and TOTP. Verification must not authorize another action, a later action, or a whole session.

### D4 — Fail closed

If Google identity validation, owner allowlisting, authenticator enrollment, secret storage, TOTP verification, expiry validation, replay prevention, or atomic one-time consumption fails, high-risk approval is denied. No fallback to the local API token, Origin header, plan ID, email OTP, SMS OTP, or an unverified identity is permitted.

## 3. Implementation security controls

These controls describe the approved direction and implementation requirements; they are not claims about current runtime behavior.

### Google identity flow

- Use OIDC Authorization Code flow with PKCE and standard `state` and `nonce` protections.
- Validate signature and applicable `iss`, `aud`, `exp`, `iat`, `nonce`, and verified-email claims.
- Enroll the single owner's stable Google `sub` through trusted setup; never auto-enroll.
- Do not request or retain Google refresh tokens unless separately approved.
- Keep application sessions separate from Google access tokens; use secure, HttpOnly, SameSite cookies and CSRF protections appropriate to the local web architecture.
- Sign-out and account revocation invalidate the local application session.

### Authenticator enrollment

- Enroll exactly one owner authenticator during trusted setup after Google owner identity has been established.
- Generate a cryptographically random TOTP secret and display its QR code only during the one-time enrollment ceremony.
- Verify enrollment by requiring a valid current TOTP before marking the authenticator active.
- Encrypt the TOTP secret at rest using an installation-held key.
- Never log or expose the secret, QR payload, or provisioning URI; do not store them in frontend persistent storage.
- Do not permit self-service authenticator replacement through an ordinary authenticated session alone.
- If the phone/device is lost, replacement requires a separately approved trusted-setup procedure. No email/SMS OTP recovery, recovery codes, secondary Master User, or automatic fallback is provided.

### TOTP profile and challenge

| Control | Requirement |
|---|---|
| Standard | RFC 6238 TOTP; interoperable HMAC-SHA1 profile |
| Code | 6 numeric digits |
| Time step | 30 seconds |
| Clock tolerance | Current time step plus/minus at most one step |
| Use | One successful verification per accepted time step |
| Attempts | Maximum 5 failed attempts per challenge window, with bounded owner/session rate limits |
| Storage | Secret encrypted at rest; no QR/provisioning URI persistence |
| Comparison | Constant-time comparison |
| Replay | Atomically record and reject an already-consumed time step |
| Logging | Never log TOTP values, QR payloads, provisioning URIs, or authenticator secrets |

The UI must show the exact action summary before requesting TOTP. It must clearly state that the code authorizes that one action only.

### Risk classification

- High-risk status is derived by backend-owned policy, never by the model or frontend.
- The model and client cannot downgrade risk or skip step-up.
- Unknown, mixed, or ambiguous actions inherit the highest applicable risk or are denied pending review.
- TOTP supplements exact-action confirmation and permission checks; it does not replace them.

## 4. Threats and limitations

TOTP avoids SMS fees, SIM-swap and carrier-delivery dependencies, but is **not phishing-resistant** and can be phished or relayed in real time. A compromised authenticator device, Google account, or local operating-system/browser session may undermine the flow.

- Do not describe TOTP as eliminating account takeover or proving absolute human presence.
- Preserve the local-first boundary; do not expose the application to the public internet as part of this decision.
- A4 must review identity, session, lost-device handling, exact-action binding, rate limits, and audit behavior before any side-effecting capability.
- WebAuthn/passkeys may be considered as a future hardening option, but are not selected by this decision.

## 5. External data flow and implementation constraints

Google sign-in requires outbound communication with Google for OIDC identity verification only. TOTP generation, enrollment verification, and action step-up are local. Do not send prompts, plans, files, machine data, or Windows telemetry to Google.

The Product Owner approved implementation on 2026-11-08. The implementation must preserve these constraints:

- OAuth client ID and secret are supplied locally through ignored `.env`; never commit or paste real credentials.
- The exact Google `sub` for the one Master User is configured explicitly. Email address is not an identity key and cannot grant or change ownership.
- The OAuth callback must be a loopback HTTP URL registered exactly in the Google Cloud OAuth client.
- Session lifetime must be explicitly configured (60–86400 seconds); no implicit lifetime is selected. Sessions are process-local and invalidated on restart. Multi-worker operation is unsupported until shared atomic storage is designed and reviewed.
- The authenticator secret is encrypted with Windows DPAPI for the current Windows user. QR data is returned once in memory and is not persisted by the frontend.
- The application cookie is HttpOnly and SameSite=Lax for the local HTTP loopback deployment. This is not a public-network deployment profile.
- Real Google credentials and a real Windows DPAPI test must be supplied/run by the Product Owner locally; tests in CI use mock OIDC and a test-only secret protector.
- No Google access/refresh token is retained after identity verification.

## 6. Scope and explicit exclusions

The Product Owner authorized the bounded F-516-01 runtime implementation on 2026-11-08. This authorization covers only Google OIDC sign-in, one Master User session, authenticator enrollment, TOTP exact-action step-up, privacy/audit integration, UI integration, and tests.

It does **not** authorize:
- SMS, SMS providers, paid messaging, email OTP, recovery codes, or a second Master User;
- Google Account recovery or a parallel recovery mechanism inside the Agent;
- self-service authenticator replacement after device loss;
- public-network exposure or mobile/remote access;
- P2 machine inspection, P3 machine-changing execution, or any real Windows command;
- Phase 6.

The existing P1 workflow remains dry-run/plan-only. If Google authentication or authenticator configuration is missing, high-risk approval must fail closed. No approval may fall back to the pre-TOTP path.

## 7. Acceptance criteria

F-516-01 can close only when all of the following are demonstrated:

- only the configured stable Google `sub` can create a Master User session;
- forged, expired, wrong-audience, wrong-issuer, wrong-nonce, replayed, or otherwise invalid Google identity responses are rejected;
- the login transaction uses state, nonce, and PKCE; Google access/refresh tokens are not retained;
- session tokens are opaque, bounded, expiring, revocable, and stored only as digests;
- only one authenticator can be enrolled; QR/provisioning material is one-time and not logged or persisted;
- authenticator secret storage is protected by Windows DPAPI and unavailable/corrupt storage fails closed;
- every high-risk approval requires a fresh TOTP challenge bound to owner, session, plan ID, immutable digest, and backend-derived risk;
- action mutation, expiry, replay, concurrent verification, wrong code, clock skew, rate limit, missing configuration, and missing secret fail closed;
- frontend never stores TOTP secrets or QR data persistently;
- local-only Host/Origin/API-token controls and dry-run-only tool boundary remain intact;
- backend, frontend, Ruff, browser E2E, and security regression checks pass;
- an independent A4 review records evidence and any residual risk;
- the Product Owner locally completes real Google OAuth and Windows DPAPI/authenticator smoke tests.

## 8. Current status and next gate

**Approved:** Google OIDC sign-in plus authenticator-app TOTP (QR enrollment) for high-risk approval. SMS, email OTP, recovery codes, and second Master User are rejected.

**Merged work:** TOTP core, exact-action step-up core, audit/privacy controls, authenticator enrollment/storage, and Google OIDC/session core (PRs #114–#118).

**In progress:** W6 runtime/API/frontend integration and regression tests on branch `feat/P5-516-01-w6-auth-runtime-integration`. This branch is not yet merged.

**Open decision:** trusted-setup replacement after loss of the authenticator device. Until a separately approved procedure exists, the Agent does not provide device replacement or self-service recovery.

**F-516-01:** OPEN — do not mark complete until W6 is merged, independent A4 review is complete, and local Windows/Google smoke tests pass.

**Phase 6 / real PC execution:** NOT AUTHORIZED. Completing F-516-01 is a prerequisite, not automatic permission to execute real machine-changing actions.
