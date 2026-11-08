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

## 5. External data flow and remaining implementation choices

Google sign-in requires outbound communication with Google for identity only. TOTP generation and verification are local and require no authenticator-vendor integration or paid messaging service. Do not send prompts, plans, files, machine data, or Windows telemetry to Google.

Remaining details to resolve before runtime implementation:
1. Google OAuth client/project ownership, redirect URI, consent configuration, and secret management.
2. Trusted-setup authenticator enrollment, encrypted secret storage/key protection, and lost-device replacement ceremony.
3. Session lifetime, reauthentication, logout, and revocation behavior.
4. Exact backend risk categories that trigger TOTP step-up.
5. Security review of the Google OIDC integration and its data-processing terms.

No provider account, credential, or production integration is selected by this document.

## 6. Scope and explicit exclusions

This decision does **not** authorize:
- implementation of Google OAuth or authenticator runtime endpoints;
- use of paid SMS, SMS provider integration, email OTP, or recovery codes;
- storage or use of real Google credentials in this documentation-only task;
- changing current approval behavior or enabling a new approval route;
- enabling P2 machine inspection or P3 machine-changing execution;
- installing software, running commands, accessing files/processes, or changing Windows settings;
- opening the local application to a public network;
- starting Phase 6.

The existing P1 workflow remains dry-run/plan-only. F-516-01 remains open until the approved design is implemented, tested, and independently reviewed.

## 7. Acceptance criteria for future implementation

A separately authorized implementation must demonstrate:
- only the enrolled Google `sub` can sign in as Master User;
- forged, expired, wrong-audience, replayed, or otherwise invalid Google identity responses are rejected;
- only the enrolled authenticator can complete step-up;
- TOTP is bound to the authenticated owner, session, and exact immutable action digest;
- action mutation, expiry, replay, concurrent verification, wrong code, clock skew, and rate-limit cases fail closed;
- no TOTP or authenticator secret appears in logs, API responses, audit events, or frontend storage;
- missing or unavailable authenticator secret cannot bypass step-up;
- lost-device replacement cannot be performed using only the same possibly compromised session;
- all local-first, backend-owned policy, exact-action confirmation, audit privacy, and dry-run-only boundaries remain intact;
- A4 security review and targeted regression tests pass before F-516-01 can be marked resolved.

## 8. Current status and next gate

**Approved:** Google sign-in plus authenticator-app TOTP (QR enrollment) for high-risk action approval; SMS delivery is rejected.

**Still requiring a separate procedure decision:** trusted-setup replacement after loss of the authenticator device.

**Not implemented:** Google OIDC and TOTP runtime behavior.

**F-516-01:** Open — approved direction recorded; implementation and independent verification remain outstanding.

**Phase 6 / real PC execution:** NOT AUTHORIZED.

Next step: reconcile the project status and Phase 5 documents, then prepare bounded, separately authorized runtime workstreams using mocked OIDC and local/test TOTP only.
