# P5-516-01 — User-Presence and Step-Up Verification Decision

## Decision record

| Field | Value |
|---|---|
| Decision ID | D-P5-516-01 |
| Finding | F-516-01 — P1 approval does not prove human presence |
| Status | **Approved direction; detailed controls proposed for review** |
| Decision owner | Product Owner |
| Decision date | 2026-11-08 |
| Repository baseline | `main` — `bdf6d51505dfe61cf492a1b333a808fd16b08935` |
| Scope | Identity sign-in and step-up confirmation design for a future exact-action approval flow |
| Change type | Documentation only |

## 1. Context

F-516-01 found that the current local API token, Origin header, plan ID, and approval request do not prove that the owner personally intended to approve an action. They protect parts of the local API boundary but are not human identity or user-presence evidence.

The Product Owner has approved this direction:

1. Sign in using **Sign in with Google** (Google account / Gmail).
2. For a high-risk action, require a second confirmation using an **SMS one-time passcode (OTP)** sent only to the phone number previously registered by the system owner.
3. Ordinary, non-high-risk interactions may use the authenticated application session, subject to existing policy and permission gates.

This decision selects the authentication direction. It does not approve a real machine-changing capability.

## 2. Approved decision

### D1 — Google sign-in

Use Google as the identity provider for application sign-in. The application must identify the owner by the stable Google OpenID Connect subject (`sub`) after validating the Google identity response. A verified email address may be displayed and used as an account attribute, but email text alone must not be the durable identity key.

Only the Google identity explicitly enrolled/allowlisted as the system owner may access the owner application.

### D2 — Registered-phone SMS step-up for high-risk approval

For every future high-risk approval, require a fresh SMS OTP sent to the single phone number enrolled by the owner. Do not allow the browser, model, request payload, or plan to nominate or replace the destination number.

A successful Google sign-in is not, by itself, approval of an action. A successful SMS OTP is also not a blanket approval: it must be bound to the exact action being approved.

### D3 — Exact-action binding

The OTP challenge must be bound server-side to all relevant identifiers for one approval attempt:

- authenticated owner identity;
- authenticated application session;
- immutable action/plan identifier and canonical action digest;
- server-derived risk classification;
- challenge identifier and expiry.

Any material change to the action or its parameters invalidates the challenge and requires a new review and OTP. OTP verification must not authorize another action, a later action, or a whole session.

### D4 — Fail closed

If Google identity validation, owner allowlisting, phone enrollment, SMS delivery, OTP verification, challenge storage, expiry validation, or atomic one-time consumption fails, the high-risk approval is denied. No fallback to the local API token, Origin header, plan ID, or an unverified phone number is permitted.

## 3. Proposed security controls for implementation review

The following are design requirements proposed for a later, separately authorized implementation. They are not claims about current runtime behavior.

### Google identity flow

- Use OpenID Connect Authorization Code flow with PKCE and the standard `state` and `nonce` protections.
- Validate the signature and the `iss`, `aud`, `exp`, `iat`, `nonce`, and verified-email claims as applicable.
- Enroll the owner's stable Google `sub` through a controlled setup process; do not auto-enroll the first account that signs in.
- Do not request or retain Google refresh tokens unless a separately approved requirement makes them necessary.
- Keep application sessions separate from Google access tokens; use secure, HttpOnly, SameSite cookies and CSRF protections appropriate to the local web architecture.
- Sign-out and account revocation must invalidate the local application session.

### Phone enrollment

- The destination is one owner-controlled phone number registered through a controlled enrollment flow.
- Verify possession of the number during enrollment before marking it active.
- Do not permit self-service phone-number changes through an ordinary authenticated session alone.
- A number change requires a separately reviewed recovery/re-enrollment process with strong owner verification and an audit event.
- Do not silently fall back to another number, email OTP, or a number supplied in an action request.

### SMS OTP challenge

Proposed defaults, to be validated during implementation planning:

| Control | Proposed requirement |
|---|---|
| Code | Cryptographically random 6-digit numeric code |
| Lifetime | 5 minutes maximum |
| Use | One successful verification only |
| Attempts | Maximum 5 failed attempts per challenge |
| Resend | Enforced cooldown and bounded resend count |
| Rate limits | Per owner, session, phone number, and source; deny on abuse |
| Storage | Store only a verifier (keyed hash/HMAC), never plaintext OTP |
| Comparison | Constant-time verification where applicable |
| Consumption | Atomic one-time transition; concurrent requests cannot both succeed |
| Logging | Never log OTP, full phone number, provider credentials, or raw challenge secrets |

The UI must show the exact action summary before requesting the OTP. The OTP screen must identify that the code is authorizing that one action, not general access or future actions.

### Risk classification

- High-risk status must be derived by backend-owned policy, not by the model or frontend.
- The model and client cannot downgrade an action's risk or skip step-up verification.
- Unknown, mixed, or ambiguous actions inherit the highest applicable risk or are denied pending review.
- SMS verification supplements the existing exact-action confirmation and permission checks; it does not replace them.

## 4. Threats and limitations

SMS is a practical step-up channel but is not phishing-resistant and is vulnerable to SIM swap, number port-out, SS7 interception, message forwarding, malware, and phone-number recycling. A compromised Google account or compromised local operating-system/browser session may also undermine the flow.

Therefore:

- Do not describe SMS OTP as eliminating account takeover or proving absolute human presence.
- Keep the current local-first boundary and do not expose the application to the public internet as part of this decision.
- Before any side-effecting capability, A4 must review the complete identity, session, recovery, exact-action binding, rate-limit, and audit design.
- Consider a stronger phishing-resistant authenticator (for example, WebAuthn/passkeys) as a future hardening option; it is not selected by this decision and must not be silently substituted for the approved SMS direction.

## 5. External data flow and unresolved implementation choices

Google sign-in and SMS delivery require outbound communication with external providers. This is a deliberate exception for identity and verification only; it does not authorize sending prompts, plans, files, or machine data to those providers.

The following remain open and must be decided before runtime implementation:

1. Google OAuth client/project ownership, redirect URI, consent configuration, and secret management.
2. SMS provider selection, country coverage, cost, delivery behavior, webhook security, and provider data retention.
3. Owner phone enrollment and recovery ceremony, including lost-phone and account-recovery scenarios.
4. Session lifetime, refresh/reauthentication policy, and logout/revocation behavior.
5. Exact backend risk categories that trigger SMS step-up.
6. Security review of the selected provider integrations and data-processing terms.

No provider, account, phone number, credential, or production integration is selected by this document.

## 6. Scope and explicit exclusions

This decision does **not** authorize:

- implementation of Google OAuth, SMS provider integration, OTP endpoints, or phone enrollment;
- storage or use of real Google/SMS credentials;
- changing current approval behavior or enabling a new approval route;
- enabling P2 machine inspection or P3 machine-changing execution;
- installing software, running commands, accessing files/processes, or changing Windows settings;
- opening the local application to a public network;
- starting Phase 6.

The existing P1 workflow remains dry-run/plan-only. The F-516-01 finding is not closed by this design record; it remains open until the approved design is implemented, tested, and independently reviewed.

## 7. Acceptance criteria for a future implementation proposal

A separately authorized implementation proposal must demonstrate:

- only the enrolled Google `sub` can sign in as owner;
- forged, expired, wrong-audience, replayed, or otherwise invalid Google identity responses are rejected;
- the OTP is sent only to the enrolled phone number;
- the OTP is bound to the authenticated owner, session, and exact immutable action digest;
- action mutation, expiry, replay, concurrent verification, wrong code, and rate-limit cases fail closed;
- no OTP or provider secret appears in logs, API responses, audit events, or frontend storage;
- SMS delivery/provider failure cannot bypass step-up verification;
- phone change and account recovery cannot be performed using only the same possibly compromised session/phone;
- all current local-first, backend-owned policy, exact-action confirmation, audit privacy, and dry-run-only boundaries remain intact;
- A4 security review and targeted regression tests pass before F-516-01 can be marked resolved.

## 8. Current status and next gate

**Approved:** Google sign-in plus SMS OTP to the owner's pre-registered phone for high-risk action approval.

**Proposed, not yet approved:** detailed protocol defaults and implementation controls in Sections 3–5.

**Not implemented:** all authentication and SMS runtime behavior.

**F-516-01:** Open — design direction recorded; implementation and independent verification remain outstanding.

**Phase 6 / real PC execution:** NOT AUTHORIZED.

Next step: Product Owner review of the detailed controls and external-provider/data-flow decisions, followed by a separate implementation task only after explicit authorization.
