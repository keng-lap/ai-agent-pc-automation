# P6-602 — Security Foundation Remediation Plan

## Status and scope

- Baseline: `d9f11ab5f400e924ebf38d6e71d6e2019e3ef423`
- Scope: security foundation remediation planning only.
- This document does not change runtime behavior or authorize real PC-changing actions.
- Historical ChatGPT review notes are candidate findings, not an independent A4 certification. Revalidate each finding against the exact source and commit before implementation.

## Verified observations at the baseline

- `authenticator.py`: DPAPI unprotect receives an allocated description pointer, but the cleanup path frees only `target.pbData`; the description allocation is not released.
- `authenticator.py`: file creation passes POSIX mode `0o600`. This alone does not establish or prove a restrictive Windows DACL. A pre-open `Path.is_symlink()` check is not a complete race-resistant reparse-point strategy.
- `oidc.py`: session expiry uses wall-clock `time.time()`; session state is process-local and intentionally invalidated on restart.
- `auth_api.py`: session cookie is HttpOnly and SameSite=Lax, with `secure=False` for current loopback HTTP.
- `step_up.py` / `totp.py`: challenge, rate-limit and replay state are process-local; elapsed-time windows use wall-clock time.
- `plan_api.py`: cached approval results are Dry Run response idempotency only, not an authorization primitive for dispatching side effects.
- `audit.py` / `auth_audit.py`: current sinks are bounded in-memory / best-effort facilities, not a durable mandatory execution ledger.

These observations do not by themselves establish exploitability in every deployment. Each implementation PR must record threat preconditions and verify the finding.

## Bounded remediation work packages

### SEC-602-01 — DPAPI native allocation cleanup
**Files:** `authenticator.py`, `tests/backend/test_authenticator.py`

- Free both DPAPI output allocations (decrypted data and optional description), including failure paths.
- Make native pointer ownership and null handling explicit.
- Preserve sanitized errors; never expose native buffer contents.

Tests:
- Windows DPAPI protect/unprotect round trip.
- Verify both returned allocations are released on success.
- Failure-path allocation cleanup.
- Existing non-Windows unit tests remain platform-independent.

Acceptance: Windows CI executes the native tests; Linux skip is not Windows evidence. Persisted ciphertext format is unchanged.

### SEC-602-02 — Windows secret-file ACL and path hardening
**Files:** `authenticator.py`, `tests/backend/test_authenticator.py`

- Establish and verify an owner-only Windows DACL; do not rely on POSIX mode bits.
- Verify effective ACLs on file and parent directory.
- Use a race-resistant Windows handle/open strategy that rejects reparse points.
- Preserve exclusive creation, atomicity and fail-closed behavior.
- Document that DPAPI current-user scope does not protect against compromise of that logged-in account.

Tests:
- Windows effective ACL assertions.
- Symlink and supported reparse-point rejection.
- Deterministic race/open-handle test seam.
- Existing exclusive-create and corrupt-file tests.

Acceptance: attach Windows-specific evidence; do not claim `0o600` secures Windows files.

### SEC-602-03 — Monotonic time for elapsed security windows
**Files:** `oidc.py`, `authenticator.py`, `step_up.py`, `totp.py` and tests

- Separate wall-clock timestamps from elapsed-time deadlines.
- Use injectable monotonic clocks for session TTL, enrollment TTL, challenge TTL and rate-limit windows.
- Retain wall-clock time for OIDC token claims, TOTP time-step calculation, externally displayed expiry timestamps and UTC audit timestamps.
- Document that process-local state is still lost on restart.

Tests:
- Wall clock moves backward/forward while monotonic time advances.
- Session, enrollment, challenge and rate-limit expiry follows elapsed time.
- OIDC claim and TOTP calculations retain wall-clock semantics.
- Invalid clock values fail closed.

Acceptance: every clock has an explicit semantic purpose; no elapsed TTL depends on wall-clock rollback.

### SEC-602-04 — Session cookie transport policy
**Files:** `auth_api.py`, configuration, auth API and browser tests

- Define supported loopback origin and cookie policy explicitly.
- Verify Secure-cookie behavior on supported localhost/loopback browsers before changing the flag.
- Never trust arbitrary forwarded headers or user-controlled Host values to select security mode.
- Keep login/logout cookie attributes symmetric, with HttpOnly, SameSite and path restrictions.

Tests:
- Cookie attributes for each supported deployment mode.
- Login/logout symmetry.
- Browser test proves cookie transmission and clearing at the supported local URL.
- Untrusted Host/proxy headers cannot weaken policy.

Acceptance: local-first deployment remains usable without weakening HTTPS behavior.

### SEC-602-05 — Enrollment lifecycle and recovery policy
**Files:** `authenticator.py`, auth API, tests, security decision record

- Revalidate pending-enrollment expiry, cleanup, replacement and capacity behavior.
- Ensure abandoned/expired enrollment cannot later be confirmed.
- Define a Product Owner-approved recovery/re-enrollment ceremony before implementing recovery.
- Do not add self-service reset, alternate-factor bypass or administrator bypass without a separate decision.

Tests:
- Expired enrollment is rejected and removed.
- Replacement invalidates the previous QR.
- Capacity and repeated-start behavior are bounded.
- Any later recovery flow requires owner re-authentication, audit and explicit confirmation.

Acceptance: enrollment state machine is documented/tested; recovery remains disabled until policy approval.

### SEC-602-06 — Approval cache and execution boundary
**Files:** `plan_api.py`, `plans.py`, `tools.py`, related tests

- Preserve safe Dry Run response idempotency.
- Explicitly prohibit cached approval responses from authorizing side-effect dispatch.
- Any future side-effecting handler requires a separate state machine that atomically consumes exact-action approval before dispatch and records immutable execution identity.
- A change to action digest, risk, package evidence or privilege requirement invalidates approval.

Tests:
- Repeated Dry Run request does not invoke its handler twice.
- Changed action cannot reuse prior approval.
- A simulated side-effect handler is never called through cached-result retrieval.
- Transaction/failure-injection tests for atomic approval consumption and dispatch intent when implemented.

Acceptance: current behavior remains Dry Run only; no side-effect handler is introduced.

### SEC-602-07 — Audit failure semantics
**Files:** `audit.py`, `auth_audit.py`, `tools.py`, tests and architecture docs

- Keep best-effort authentication diagnostics separate from mandatory execution audit.
- Define future mandatory events: proposal, approval, execution-start, completion, failure, partial/unknown outcome, cancellation and denial.
- Specify fail-closed behavior when mandatory audit cannot be committed.
- Define durable storage, integrity, access control, retention, redaction and recovery before runtime implementation.
- Never log prompts, TOTP, QR/provisioning URIs, secrets, raw command text or unnecessary machine inventory.

Tests:
- Optional auth diagnostics can fail without changing auth outcome where intended.
- Mandatory execution-audit failure blocks dispatch.
- Audit schema rejects secrets and unbounded fields.
- Redaction and retention limits are enforced.

Acceptance: current in-memory sinks are not described as a durable security ledger; mandatory audit is a prerequisite for side effects.

### SEC-602-08 — Process-local state and deployment guardrails
**Files:** `oidc.py`, `step_up.py`, `totp.py`, startup/configuration, tests and deployment docs

- Explicitly enforce/document single-process deployment while security state remains process-local.
- Prevent multi-worker deployment from being described as supported.
- Define durable atomic state requirements before multi-worker or restart-resilient execution.
- Do not add shared persistence in this planning task.

Tests:
- Reject unsupported worker configuration where enforceable.
- Deployment docs and health diagnostics expose the single-process constraint.
- Restart invalidation is tested and documented.

Acceptance: no multi-worker/restart-safe guarantee until shared atomic storage is implemented and reviewed.

## Parallel work lanes

| Lane | Work | Primary files | Coordination |
|---|---|---|---|
| A | SEC-602-01 DPAPI cleanup | `authenticator.py`, authenticator tests | Independent |
| B | SEC-602-03 clock semantics | `oidc.py`, `step_up.py`, `totp.py` and tests | Agree clock contract first |
| C | SEC-602-04 cookie policy | `auth_api.py`, auth/browser tests | Browser matrix required |
| D | SEC-602-06/07 approval and audit | `plan_api.py`, `audit.py`, `auth_audit.py`, tools/tests | No side effects |
| E | SEC-602-02 Windows file hardening | `authenticator.py`, Windows tests | Serialize with A and F |
| F | SEC-602-05 enrollment lifecycle | `authenticator.py`, auth tests | Serialize with A and E |
| G | SEC-602-08 deployment guardrails | startup/config/docs/tests | Align with B |

Parallel branches must not modify the same file concurrently without an agreed integration order. Lanes A, E and F must be serialized or split into non-overlapping commits.

## PR discipline

Every remediation PR must:
1. Name finding IDs and exact base SHA.
2. Stay narrowly scoped; no opportunistic refactor.
3. Include regression, negative and failure-path tests.
4. Run relevant backend tests and Ruff; frontend/browser tests when cookie behavior changes.
5. Attach Windows-specific CI evidence for DPAPI, ACL and reparse-point changes.
6. Report skipped/not-run checks explicitly.
7. Preserve loopback-only operation and Dry Run-only PC actions.
8. Receive separate review; no self-certification as A4.
9. Remain unmerged until CI passes and the user approves merge, unless documentation-only merge authority is explicitly delegated.

## Release gate

Security Foundation is not complete until every applicable finding has verified threat preconditions, implementation, regression tests, CI evidence, independent A4 re-review and required Product Owner approval.

**Hard prohibition:** This plan does not enable installers, package managers, arbitrary shell/scripts, admin operations or any other real PC-changing capability.
