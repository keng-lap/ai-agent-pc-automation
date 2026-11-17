# PR #165 — P6-601 Authenticator / Session Security Review Status

## Scope reset

This document supersedes the earlier review text that covered TOTP recovery, secret replacement, Google reauthentication freshness, and WebAuthn. Those features have been removed from the proposed PR scope.

The current intended scope is limited to:

- Google OIDC as the primary sign-in mechanism and the existing Google application session.
- One-time TOTP enrollment for the authenticated Master User.
- TOTP Step-up for exact-action-bound high-risk approvals.
- Windows current-user DPAPI protection and owner-only secret-file storage.
- Plan Review / Approval and Dry Run only; no worker dispatch or machine-changing operation.

TOTP recovery/replacement, recovery codes, WebAuthn/platform-authenticator ceremonies, and alternate-factor fallback are explicitly out of scope.

## Review status

**Disposition: REVIEW REQUIRED — this document is not merge approval.**

The previous static review is not valid evidence for the revised implementation because it assessed code paths that are now being removed. A fresh review must be performed against the final PR head after the removal work and CI complete.

This document is not a named human A4 sign-off, penetration test, or Product Owner approval. No new review result is claimed here.

## Required checks before merge

1. Confirm the PR diff contains no recovery/replacement endpoints, no WebAuthn/platform-authenticator module or dependency, and no recovery UI.
2. Confirm Google OIDC login and existing application-session behavior remain unchanged.
3. Confirm TOTP enrollment remains one-time, owner-bound, session-bound, and fails closed on storage errors.
4. Confirm Step-up remains mandatory for high-risk approval and is bound to the exact immutable plan/action digest.
5. Confirm Windows DPAPI, owner SID/DACL verification, and reparse-point rejection tests pass on Windows CI.
6. Confirm backend tests, Ruff, frontend unit tests, frontend build, and relevant Windows workflows pass on the exact final PR head.
7. Obtain a fresh CodeRabbit review and address any actionable findings.
8. Complete acceptance on the target Windows 11 Home machine before merge if that remains a required project gate.

## Explicit safety boundary

The PR does not authorize a worker, background execution, WinGet invocation, installer execution, arbitrary shell/script execution, remote/LAN control, or host mutation. Approval remains Dry Run only.

Sessions, OIDC transactions, Step-up challenges, and TOTP replay state remain process-local; multi-worker deployment is unsupported. Same-user malware and a fully compromised Windows account remain outside the protection boundary.
