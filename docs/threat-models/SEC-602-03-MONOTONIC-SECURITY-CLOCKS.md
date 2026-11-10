# Threat Model — SEC-602-03 Monotonic Time for Elapsed Security Windows

- **Status:** Draft — implementation and regression tests pending
- **Date:** 2026-11-10
- **Base commit:** b9dbf544921de4c86cb1d3c555a739e26f558ec8
- **Scope:** OIDC transaction TTL, application session TTL, TOTP enrollment TTL, step-up challenge TTL, owner/session rate-limit windows, and their clock dependencies.
- **Related plan:** `docs/P6-602-SECURITY-FOUNDATION-REMEDIATION-PLAN.md`
- **Secure development policy:** `docs/SECURE-DEVELOPMENT-STANDARD.md`

## 1. Objective

Prevent wall-clock adjustments from extending, prematurely expiring, or otherwise corrupting elapsed-time security windows. Use an injectable monotonic clock for durations measured within one process. Retain wall-clock time only where protocol semantics or externally meaningful timestamps require it.

This change does not make process-local state durable and does not make multi-worker deployment safe.

## 2. Assets and security objectives

| Asset | Security objective |
|---|---|
| OIDC state/nonce/PKCE transaction | One-time use and bounded lifetime unaffected by wall-clock rollback |
| Application session | Absolute elapsed TTL cannot be extended by wall-clock rollback |
| Pending TOTP enrollment | Expiry and one-time QR lifecycle cannot be extended by wall-clock rollback |
| Step-up challenge | Exact-action challenge expiry cannot be extended by wall-clock rollback |
| Owner/session failed-attempt window | Rate-limit duration cannot be extended or bypassed by wall-clock changes |
| TOTP time-step and OIDC token claims | Continue to follow protocol-defined wall-clock semantics |

## 3. Trust boundaries and clock sources

Two clock domains must remain explicit:

- **Wall clock** (`time.time`): UTC/Unix timestamps, OIDC `iat`/`exp` validation, TOTP RFC 6238 time-step calculations, audit timestamps, and externally displayed `created_at`/`expires_at` values.
- **Monotonic clock** (`time.monotonic`): elapsed durations within the current process, including transaction/session/enrollment/challenge TTLs and rate-limit windows.

Monotonic values MUST NOT be serialized as UTC timestamps, returned as user-facing expiry values, compared to OIDC claims, or persisted for recovery across process restarts.

## 4. Threats and abuse cases

| ID | Threat | Preconditions | Impact | Required mitigation | Tests |
|---|---|---|---|---|---|
| T-01 | Wall clock moves backward after session creation | Local clock adjustment or time sync correction | Session remains valid longer than configured TTL | Session expiry uses monotonic deadline | C-SESSION-01 |
| T-02 | Wall clock moves backward after challenge/transaction/enrollment creation | Same | One-time security artifacts live longer than intended | Each elapsed TTL uses monotonic deadline | C-OIDC-01, C-ENROLL-01, C-STEPUP-01 |
| T-03 | Wall clock jumps forward | Same | Valid sessions/challenges unexpectedly expire early | Elapsed TTL unaffected; protocol claim checks still use wall clock | C-CLOCK-01 |
| T-04 | Monotonic clock is invalid or regresses in injected test/platform seam | Clock adapter defect or invalid test input | Expiry bypass or inconsistent state | Validate finite numeric samples; fail closed on invalid values; monotonic source is platform contract | C-CLOCK-02 |
| T-05 | Monotonic deadline leaks into public timestamp or protocol claim comparison | Implementation mixes clock domains | Invalid expiry display or OIDC/TOTP behavior | Keep separate fields and types/names for monotonic deadlines and wall timestamps | C-BOUNDARY-01 |
| T-06 | Restart or multi-worker deployment treated as monotonic continuity | Process-local state is recreated | Security state is lost; deadlines cannot be reconstructed | Document process-local invalidation and single-process constraint; no false durability guarantee | C-RESTART-01 |

## 5. Security invariants

- Every elapsed-time security window MUST use a monotonic deadline.
- Every object exposed to callers MUST retain wall-clock timestamps only for display/protocol compatibility; monotonic deadlines remain private.
- OIDC `iat` and `exp` validation MUST continue using wall-clock time.
- TOTP RFC 6238 time-step calculation MUST continue using wall-clock time.
- Rate-limit window elapsed time MUST use monotonic time.
- Invalid/non-finite clock values MUST fail closed.
- Clock dependencies MUST be injectable independently so tests can move wall and monotonic clocks separately.
- No monotonic timestamp may be persisted or interpreted across process restarts.
- Existing process-local state and restart invalidation behavior MUST be documented; this work does not claim durable replay or challenge state.

## 6. Implementation design constraints

1. Introduce a separate injectable monotonic clock for each stateful component (default `time.monotonic`).
2. Capture wall time and monotonic time at creation when both are required.
3. Store monotonic deadlines privately alongside public wall-clock expiry metadata.
4. On consume/resolve/confirm/verify, compare only monotonic now to monotonic deadline.
5. For owner/session failure windows, store monotonic window-start values and compare elapsed durations only in that domain.
6. Keep TOTP replay step calculation tied to wall time; do not silently convert RFC 6238 time to monotonic time.
7. Preserve existing constructor injection compatibility where practical; update tests explicitly when clock injection semantics change.
8. Avoid broad refactoring or changing token/secret formats.

## 7. Verification plan

| Test ID | Scenario | Expected result |
|---|---|---|
| C-OIDC-01 | Wall clock moves backward while monotonic advances beyond transaction TTL | Transaction rejected as expired |
| C-SESSION-01 | Wall clock moves backward while monotonic advances beyond session TTL | Session rejected |
| C-ENROLL-01 | Wall clock moves backward while monotonic advances beyond enrollment TTL | Pending enrollment rejected and removed |
| C-STEPUP-01 | Wall clock moves backward while monotonic advances beyond challenge TTL | Challenge rejected/expired |
| C-CLOCK-01 | Wall clock jumps forward while monotonic remains within TTL | Elapsed-time state remains valid; OIDC/TOTP protocol checks still follow wall time |
| C-CLOCK-02 | Clock adapter returns NaN, infinity, bool, non-number, or invalid monotonic progression | Operation fails closed without consuming/creating unsafe state |
| C-BOUNDARY-01 | Inspect public expiry fields and protocol validation | Public timestamps remain wall-clock values; monotonic values are never exposed |
| C-RESTART-01 | Recreate process-local stores | State invalidation remains explicit; no claim of restart continuity |

Tests must use independent fake wall and monotonic clocks. Include boundary checks at exactly the TTL deadline and immediately before it. Include failure injection to prove state is not consumed when clock validation fails.

## 8. Non-goals and residual risks

- No durable/shared challenge, session, enrollment, or replay storage.
- No multi-worker support.
- No protection against an attacker with full control of the process or OS clock source beyond the elapsed-time semantics described.
- Monotonic clock continuity across suspend/resume is platform-dependent; supported Windows behavior must be documented and tested if suspend duration is security-relevant.
- TOTP and OIDC protocol validity still depends on trustworthy wall-clock synchronization.

## 9. Review disposition

- [ ] Clock-domain mapping reviewed for every call site
- [ ] Existing constructor/API compatibility assessed
- [ ] Negative and boundary tests implemented
- [ ] Wall-clock protocol semantics preserved
- [ ] Monotonic TTL behavior tested independently
- [ ] Restart and single-process limits documented
- **Disposition:** BLOCKED pending implementation, test evidence, and independent review
