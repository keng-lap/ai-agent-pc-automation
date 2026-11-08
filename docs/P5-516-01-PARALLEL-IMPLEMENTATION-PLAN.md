# P5-516-01 — Parallel Implementation Plan

## Purpose

Turn the approved F-516-01 direction into independently reviewable implementation workstreams while preserving the current local-first, dry-run-only safety boundary.

Approved direction:
- Google OpenID Connect sign-in; owner identity keyed by the enrolled Google `sub`.
- High-risk approval requires a fresh SMS OTP sent only to the owner's pre-registered phone number.
- OTP approval is bound to one immutable action and does not authorize a session or future actions.
- Exactly one Master User owns the installation. The Master User is provisioned during trusted setup and bound to one explicitly enrolled Google account; ordinary users and admins cannot promote themselves or create another Master User.
- Account recovery sends a one-time confirmation code to the email address on the same enrolled Google account; the user must enter the code to complete the recovery step. The destination is not user-selectable during recovery. No recovery codes or secondary admin account are provided.

This document is a work breakdown and dependency plan. It does not select vendors, approve credentials or production integrations, or authorize runtime changes.

## Parallel workstreams

| ID | Workstream | Can proceed in parallel? | Required interface / dependency | Deliverable |
|---|---|---|---|---|
| W1 | Google OIDC sign-in and single-Master-User allowlist | Yes | Existing local web-app session boundary; trusted owner provisioning decision | OIDC adapter contract, callback/session design, single-owner enforcement, mocked tests |
| W2 | Registered phone enrollment and recovery | Design can proceed in parallel; runtime wiring depends on W1 identity | Stable owner identity; recovery ceremony decision | Phone enrollment/recovery state machine, Google-account email confirmation flow, threat model, tests |
| W3 | OTP challenge service and SMS provider adapter | Core challenge logic can proceed in parallel using a fake provider; delivery integration depends on W2 and provider selection | Registered destination interface; provider contract | Challenge lifecycle, one-time atomic consume, rate limits, fake-provider tests |
| W4 | Exact-action binding and backend risk gate | Yes, in parallel with W1-W3 | Current plan/approval contract and backend policy | Canonical action digest, server-owned risk decision, mutation/replay tests |
| W5 | Audit and privacy verification | Yes, in parallel | Existing bounded audit sink and event schema | Events for sign-in/step-up outcomes; redaction and no-secret tests |
| W6 | Integration and independent A4 review | No; integration follows W1-W5 contracts | All workstream contracts and passing targeted tests | Integrated test evidence and independent security review |

## Parallel execution rules

1. Each workstream must use its own branch and PR. Do not have parallel workstreams edit the same files without an explicit ownership handoff.
2. Before implementation, map file ownership and shared interfaces. Prefer small adapter interfaces and contract tests over concurrent edits to shared modules.
3. W1, W2 design, W3 provider-independent challenge logic, W4, and W5 can be developed independently behind interfaces and test doubles.
4. Integrate in dependency order: W1 identity contract; W2 phone enrollment; W3 SMS delivery wiring; W4 final approval gate; W5 audit integration; then W6.
5. Any interface change must be communicated and reviewed before dependent branches rebase or merge.
6. Merge only when all required CI checks for the exact PR head are completed and successful. Re-check head SHA and mergeability immediately before merge.
7. No workstream may weaken existing policy, approval, local-origin, privacy, or dry-run controls to make tests pass.

## Decisions still required before provider-connected runtime work

- Google Cloud project / OAuth client ownership, redirect configuration, and secret handling.
- SMS provider, Thailand delivery support, pricing, delivery receipts, webhook authentication, and retention.
- Phone enrollment and lost-phone recovery procedure. Account recovery email confirmation is decided: send a single-use, short-lived code to the email on the enrolled Google account and require successful entry. This confirms access to that mailbox; it is not an independent factor if the Google account itself is compromised, and it must not silently replace or change the enrolled phone number. No recovery code and no secondary Master User are in scope. If the sole Master User loses access to the enrolled Google account, there is intentionally no self-service fallback; any future owner-transfer procedure requires a separately approved, audited design.
- Session lifetime and reauthentication rules.
- Exact backend risk categories that trigger SMS step-up.
- Whether any external provider communication is allowed in the target deployment and how it is disclosed.

Use mock providers and test credentials only until these decisions and a separate implementation authorization are recorded. Never commit real credentials.

## Safety gates

- Keep the application local-first; do not expose it to the public internet.
- Do not send prompts, plans, files, machine data, or Windows telemetry to Google or SMS providers.
- Google login is identity authentication, not action approval.
- SMS OTP is a single-action step-up check, not proof against SIM swap or a phishing-resistant factor.
- OTP must be cryptographically random, short-lived, single-use, rate-limited, bound to owner + session + exact action digest, and atomically consumed.
- Fail closed on provider, storage, verification, expiry, replay, or rate-limit failure.
- Never log OTPs, full phone numbers, provider secrets, or raw challenge secrets.
- Do not implement P2 machine inspection, P3 machine-changing execution, or Phase 6 under this plan.

## Completion criteria

Each W1-W5 PR must include focused unit/contract tests and document its interface. The integration PR must demonstrate negative cases (wrong owner, invalid OIDC response, unregistered destination, wrong/expired/replayed OTP, action mutation, concurrent consume, provider failure, and rate-limit exhaustion), privacy checks, and regression coverage for existing plan-only behavior.

F-516-01 remains open until the integrated design is implemented, tested, and independently reviewed by A4. This plan does not close the finding or authorize real PC execution.
