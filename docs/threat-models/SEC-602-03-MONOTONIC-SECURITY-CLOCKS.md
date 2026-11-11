# Threat Model — SEC-602-03 Monotonic Security Deadlines

- **Status:** Implementation proposal; CI and independent A4 review pending
- **Base commit:** `95320f4422a54349df1bcac7c665f7f9e88c607b`
- **Scope:** OIDC transaction expiry, application-session TTL, TOTP enrollment TTL, step-up challenge TTL, and owner/session TOTP failure windows.
- **Non-goals:** No persistence change, multi-worker support, authentication-policy change, cookie-policy change, or real PC-changing capability.

## Threat

Elapsed security windows were calculated from wall-clock timestamps. If the system clock moves backward, a still-valid in-memory record can remain usable longer than its configured TTL. A backward adjustment can also affect the owner/session failed-TOTP window and weaken rate limiting.

## Security contract

- Use wall-clock time only for externally meaningful timestamps, OIDC token claim validation, and TOTP time-step calculation.
- Use a monotonic clock for elapsed TTLs and rate-limit windows.
- Keep public `expires_at` values as wall-clock timestamps for UI/API compatibility; keep a separate monotonic deadline internally.
- Production defaults use `time.monotonic()`; wall-clock injection remains available for deterministic tests.
- Invalid elapsed-clock values fail closed.
- Challenge expiry and failed-attempt state remain process-local and are lost on restart. This change does not claim restart resilience or multi-worker safety.

## Changed state machines

| State | Elapsed-time control |
|---|---|
| OIDC authorization transaction | One-time state expiry |
| Application session | Session TTL |
| TOTP enrollment | Pending enrollment TTL |
| Step-up challenge | Challenge TTL |
| Owner/session failures | Five-minute failed-attempt window |

TOTP verification continues to receive wall-clock time because RFC 6238 time steps are wall-clock based. The monotonic clock is not substituted into TOTP code generation or ID-token claim validation.

## Verification

Regression tests move wall time backward while independently advancing monotonic time, then assert that:
- expired OIDC transactions and sessions are rejected;
- expired authenticator enrollments and step-up challenges are rejected;
- failed-TOTP rate limits do not reset due to wall-clock rollback.

CI must pass backend tests and Ruff. This is not independent A4 certification. Windows-specific ACL/path findings and DPAPI platform behavior are outside this change.

## Residual limitations

- In-memory state is process-local and disappears on restart.
- A monotonic clock is process/boot scoped; persisted monotonic deadlines must not be introduced.
- Production multi-worker deployment still requires shared atomic state.
- No real installation, removal, shell, script, administrator, or other PC-changing handler is introduced.
