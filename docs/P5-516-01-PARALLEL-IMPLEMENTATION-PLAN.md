# P5-516-01 — Parallel Implementation Plan

## Purpose

Turn the approved F-516-01 direction into independently reviewable implementation workstreams while preserving the current local-first, dry-run-only safety boundary.

Approved direction:
- Google OpenID Connect sign-in; owner identity keyed by the enrolled Google `sub`.
- High-risk approval requires a fresh TOTP code from the owner's enrolled authenticator app, provisioned by scanning a one-time QR code during trusted setup.
- TOTP step-up approval is bound to one immutable action and does not authorize a session or future actions.
- Exactly one Master User owns the installation. The Master User is provisioned during trusted setup and bound to one explicitly enrolled Google account; ordinary users and admins cannot promote themselves or create another Master User.
- Google Account recovery is handled entirely by Google's own account-recovery process. The AI Agent does not implement a parallel Google-account recovery flow, send Gmail recovery OTPs, or override Google's recovery decisions.
- If the Master User permanently loses access to the enrolled Google Account and cannot recover it through Google, the installation has no self-service fallback. Any future owner-transfer procedure requires a separately approved, audited design. No recovery codes or secondary Master User are provided.

This document is a work breakdown and dependency plan. It does not select vendors, approve credentials or production integrations, or authorize runtime changes.

## Parallel workstreams

| ID | Workstream | Can proceed in parallel? | Required interface / dependency | Deliverable |
|---|---|---|---|---|
| W1 | Google OIDC sign-in and single-Master-User allowlist | Yes | Existing local web-app session boundary; trusted owner provisioning decision | OIDC adapter contract, callback/session design, single-owner enforcement, mocked tests |
| W2 | Authenticator enrollment and lost-device handling | Design can proceed in parallel; runtime wiring depends on W1 identity | Stable owner identity; trusted setup and separately approved replacement policy | QR enrollment state machine, encrypted secret storage, lost-device threat model and tests |
| W3 | TOTP challenge service | Core verification logic can proceed in parallel using test secrets; enrollment integration depends on W2 | Enrolled TOTP secret interface | TOTP validation, one-time time-step consume, clock-window policy, rate limits and tests |
| W4 | Exact-action binding and backend risk gate | Yes, in parallel with W1-W3 | Current plan/approval contract and backend policy | Canonical action digest, server-owned risk decision, mutation/replay tests |
| W5 | Audit and privacy verification | Yes, in parallel | Existing bounded audit sink and event schema | Events for sign-in/step-up outcomes; redaction and no-secret tests |
| W6 | Integration and independent A4 review | No; integration follows W1-W5 contracts | All workstream contracts and passing targeted tests | Integrated test evidence and independent security review |

## Parallel execution rules

1. Each workstream must use its own branch and PR. Do not have parallel workstreams edit the same files without an explicit ownership handoff.
2. Before implementation, map file ownership and shared interfaces. Prefer small adapter interfaces and contract tests over concurrent edits to shared modules.
3. W1, W2 design, W3 provider-independent challenge logic, W4, and W5 can be developed independently behind interfaces and test doubles.
4. Integrate in dependency order: W1 identity contract; W2 trusted authenticator enrollment and lost-device policy; W3 TOTP challenge core; W4 final approval gate; W5 audit integration; then W6.
5. Any interface change must be communicated and reviewed before dependent branches rebase or merge.
6. Merge only when all required CI checks for the exact PR head are completed and successful. Re-check head SHA and mergeability immediately before merge.
7. No workstream may weaken existing policy, approval, local-origin, privacy, or dry-run controls to make tests pass.

## Decisions still required before provider-connected runtime work

- Google Cloud project / OAuth client ownership, redirect configuration, and secret handling.
- Authenticator enrollment and lost-device replacement procedure. Google Account recovery itself is exclusively Google's responsibility; the AI Agent must not build a parallel Gmail OTP or Google-account recovery mechanism.
- Session lifetime and reauthentication rules.
- Exact backend risk categories that trigger TOTP step-up.
- Whether any external provider communication is allowed in the target deployment and how it is disclosed.

Use a mocked OIDC provider and test-only TOTP secrets until the remaining decisions and a separate runtime implementation authorization are recorded. Never commit real credentials.

## Safety gates

- Keep the application local-first; do not expose it to the public internet.
- Do not send prompts, plans, files, machine data, or Windows telemetry to Google or any external identity service.
- Google login is identity authentication, not action approval.
- TOTP is a single-action step-up check, not phishing-resistant; phishing and real-time relay risks remain.
- TOTP secrets must be generated with a cryptographically secure random source, shown only through a one-time enrollment QR/provisioning URI, encrypted at rest, and never logged.
- TOTP verification must use a defined clock-skew window, prevent reuse of an accepted time-step, be rate-limited, bound to owner + session + exact action digest, and atomically consumed.
- Fail closed on identity-provider, secret-storage, verification, expiry, replay, or rate-limit failure.
- Never log TOTP values, provisioning URIs, QR payloads, or authenticator secrets.
- Do not implement P2 machine inspection, P3 machine-changing execution, or Phase 6 under this plan.

## Completion criteria

Each W1-W5 PR must include focused unit/contract tests and document its interface. The integration PR must demonstrate negative cases (wrong owner, invalid OIDC response, unenrolled authenticator, wrong/expired/replayed TOTP, clock-skew boundaries, action mutation, concurrent consume, secret-storage failure, and rate-limit exhaustion), privacy checks, and regression coverage for existing plan-only behavior.

F-516-01 remains open until the integrated design is implemented, tested, and independently reviewed by A4. This plan does not close the finding or authorize real PC execution.
