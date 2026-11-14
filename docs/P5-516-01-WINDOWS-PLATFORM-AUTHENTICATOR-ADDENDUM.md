# P5-516-01 Addendum — Windows Platform Authenticator for Local User Presence

**Status:** Product Owner approved on 2026-11-14. Implementation is not yet complete.
**Scope:** Local Windows application only. This addendum supersedes the earlier decision that WebAuthn was merely a future option, but only for the narrowly defined ceremonies below.

## Decision

1. Google OpenID Connect remains the sole primary application sign-in mechanism and continues to establish the allowlisted Master User session.
2. The existing Authenticator App (TOTP) remains the Step-up factor for high-risk action approvals. This addendum does not replace, weaken, or bypass TOTP Step-up.
3. WebAuthn using a browser platform authenticator is added as a local user-presence / user-verification factor for initial TOTP setup and subsequent TOTP replacement.
4. The browser requests `authenticatorAttachment: "platform"` and `userVerification: "required"`. The server must verify the WebAuthn ceremony with a maintained implementation and enforce the exact configured origin, RP ID, challenge, credential, owner, session, ceremony purpose, expiry, and one-time use.
5. A valid Google application session alone must never authorize TOTP replacement. A previously registered WebAuthn credential assertion is required for self-service recovery.
6. A WebAuthn credential must be registered during a trusted setup ceremony while the owner has a valid Google session. Registration is one-time / explicitly authorized; a Google session alone cannot silently replace an existing WebAuthn credential.
7. If both the TOTP device and the registered platform authenticator are lost, self-service recovery is unavailable. The application must fail closed and require a separately designed, owner-controlled local trusted-setup procedure. No email/SMS OTP, recovery code, second Master User, or automatic fallback is introduced.
8. Do not disable Google OIDC ID-token validation, relax `auth_time` validation globally, or substitute `iat` for `auth_time`. Ordinary Google login remains unchanged. Any legacy migration path must be explicitly specified and reviewed; it must not silently treat an existing Google session as the second factor.
9. Do not claim that WebAuthn cryptographically identifies Windows Hello specifically. The browser requests a platform authenticator and required user verification; on supported Windows browsers this is expected to invoke Windows Hello, but the WebAuthn assertion identifies a platform authenticator, not necessarily a uniquely branded Windows Hello implementation.

## Ceremony and state requirements

### Initial trusted setup

- Require the existing Google OIDC Master User session.
- Create a cryptographically random, short-lived, one-use server challenge bound to the owner, session, RP ID, origin, and registration purpose.
- Use WebAuthn registration options with platform attachment and required user verification.
- Verify attestation/registration response server-side, including challenge, origin, RP ID hash, flags, credential public key, credential ID, and user handle.
- Persist the credential public key and metadata in owner-protected local storage. Never persist private key material; it remains in the platform authenticator.
- Only after registration succeeds may the TOTP enrollment ceremony begin. TOTP secret persistence remains protected by the existing Windows DPAPI storage path.
- Reject duplicate, unexpected, expired, replayed, cross-session, cross-owner, or wrong-purpose ceremonies.

### TOTP replacement / recovery

- Require a valid Google Master User application session.
- Require a fresh WebAuthn assertion from a credential already registered for this owner. Require user verification and verify the challenge, signature, RP ID, origin, credential ownership, session binding, expiry, and one-time consumption.
- Only after successful assertion may the replacement TOTP QR be issued.
- Keep the currently active TOTP secret until the replacement TOTP has been confirmed and atomically committed.
- Preserve TOTP replay protection and existing Step-up verification semantics. Audit every allowed and denied recovery transition without logging secrets, QR payloads, challenges, assertions, or tokens.
- Rotate the application session after successful replacement; handle uncertain persistence outcomes fail-closed.

### Local origin / RP configuration

- Determine the actual frontend origin(s) and bind WebAuthn to an exact configured origin and RP ID. Do not infer them from untrusted Host or Origin headers.
- `localhost` and `127.0.0.1` are distinct origins and must not be mixed. If the frontend supports both, choose one canonical origin or explicitly register and validate a narrowly enumerated origin set with a compatible RP ID.
- Localhost is a WebAuthn secure context in modern browsers. Browser support and actual Windows 11 Home + Chrome/Edge + Windows Hello behavior remain manual acceptance requirements.

## Security and implementation constraints

- Use a maintained server-side WebAuthn library for CBOR/COSE parsing and cryptographic verification; do not implement these primitives manually.
- Store credential public keys and metadata with owner-only Windows ACL protections and integrity checks. Do not place them in a broadly writable directory.
- Challenge storage must be bounded, short-lived, one-use, purpose-bound, owner-bound, session-bound, and protected against concurrent replay.
- Enforce request size limits, strict schemas, rate limits, CSRF/origin protections, no-store responses, and sanitized errors.
- Treat signature-counter behavior according to WebAuthn library/spec guidance; do not reject valid synced/platform authenticators solely because a counter remains zero.
- No remote/LAN control, worker dispatch, WinGet invocation, installer execution, arbitrary shell/script execution, or machine-changing operation is authorized by this decision.
- PR #165 remains open and unmerged. No automatic approval or merge.

## Acceptance criteria

- Google login and ordinary session behavior are unchanged.
- TOTP Step-up remains mandatory for every currently defined high-risk action and existing replay tests remain valid.
- Registration succeeds only for the authenticated Master User with a platform authenticator and required user verification.
- Registration rejects wrong origin/RP ID, invalid or expired challenge, replay, wrong owner/session/purpose, malformed attestation, and duplicate credential replacement.
- Recovery succeeds only with a previously registered credential and valid user-verified assertion.
- Recovery rejects a Google session without WebAuthn proof, a credential belonging to another owner, wrong origin/RP ID, invalid signature, expired/replayed challenge, missing user verification, and cross-session use.
- The existing TOTP secret remains active until replacement confirmation and durable commit succeed.
- Lost TOTP + lost platform credential fails closed; no weaker web fallback exists.
- Unit tests cover challenge lifecycle, origin/RP binding, session/owner/purpose binding, replay/concurrency, signature and flag validation, persistence corruption, and failure paths.
- Frontend tests cover native WebAuthn API success, cancellation, unsupported browser, and malformed responses.
- CI passes on the exact updated PR head.
- Manual acceptance is recorded on the target Windows 11 Home machine using the intended browser and Windows Hello.
- A fresh independent security review is completed before Product Owner merge approval.
