# PR #165 — P6-601 Authenticator / Session Security Review

## Review identity and limits

**Disposition: PASS WITH CONDITIONS — do not merge solely on this report.**

This is ChatGPT's secondary, static A4-style security review. CodeRabbit remains the primary automated PR reviewer. This report is not a named human A4 sign-off, penetration test, or Product Owner approval.

| Field | Value |
|---|---|
| Repository | `keng-lap/ai-agent-pc-automation` |
| Pull request | [#165](https://github.com/keng-lap/ai-agent-pc-automation/pull/165) |
| Reviewed source HEAD | `0413c62d10bb6309f6d764350177f6cf8df62bc3` |
| Base SHA | `96e4d0dc5ad6d920438056e33909d615937934fd` |
| Review date | 2026-11-14 |
| Scope | OIDC, sessions, TOTP, Step-up, enrollment/recovery, Windows DPAPI secret storage, configuration path boundary, related frontend, tests and P6-601 documents |
| Method | Read-only static source/diff review plus inspection of GitHub Actions results. No local tests or live Windows operations were performed. |

This report supersedes the earlier PR-165 review that referenced an older source revision.

## Executive assessment

The reviewed implementation preserves Google OIDC as primary authentication and uses TOTP only as a Step-up factor. The reviewed paths do not introduce arbitrary shell/PowerShell/CMD/script execution, dynamic handler selection, installer invocation, or host mutation.

The previously identified replay, shared-directory DACL, and post-persistence session-rotation issues have been addressed in the current source. The five earlier CodeRabbit findings also have corresponding code/documentation changes. No Critical or High vulnerability was verified in the reviewed scope.

The main remaining technical limitation is that Windows replacement now uses a full-path `MoveFileExW` rename while all verified parent directories remain pinned without `FILE_SHARE_DELETE`. The dedicated directory is owner-only, and same-user malware is explicitly outside the protection boundary. This is a documented trade-off from the prior handle-relative rename implementation, which returned success on a hosted Windows runner while leaving the old destination payload in place. The replacement path verifies the source and exact destination payload and requests write-through.

## Findings and remediation status

### F-01 — Medium — TOTP replay across Recovery and Step-up

**Status: Addressed.**

Recovery now passes the exact matched RFC 6238 step to `TotpReplayGuard.consume_step_after()` on the primary owner replay key. The replay lock is held while secret replacement runs, so concurrent Step-up cannot consume the same step between persistence and replay-state advancement. If persistence raises, the primary replay state is not advanced.

Regression coverage includes future-step recovery replay against the primary guard and persistence failure preserving the old secret and primary replay state.

### F-02 — Medium — DACL mutation of an arbitrary/shared parent directory

**Status: Addressed.**

The secret path is now restricted by `validate_authenticator_secret_path()` to a direct child of the dedicated application-owned `.agent-state/authenticator` directory. Validation occurs in both environment configuration and `build_auth_services()`, so directly constructed Settings cannot bypass the boundary. The Windows adapter therefore does not apply its directory DACL to an arbitrary configured/shared parent. Existing reparse-point and owner verification remains in place.

Regression coverage rejects a configured secret path outside the dedicated directory. The security document and `.env.example` state the new path requirement.

### F-03 — Low — Session rotation failure after secret persistence

**Status: Addressed.**

If the secret has been persisted but session rotation returns `None`, the endpoint now reports the authenticator change as successful and records the success event rather than returning a misleading 401. No replacement cookie is issued in this case; the owner may need to sign in again. The frontend refreshes session status after successful confirmation and reflects an expired session accurately when the status request succeeds.

A regression test verifies persisted secret state and a success audit event when rotation fails.

### F-04 — Low — Temporary and partial secret-file residue

**Status: Mitigated; cleanup remains best-effort.**

Incomplete first writes are deleted after the file handle closes while the verified parent directory remains pinned. Failed replacement attempts remove their randomly named temporary file while the parent remains pinned. If the filesystem refuses cleanup, inert DPAPI ciphertext may remain in the owner-only directory; this residual is documented. No automated general-purpose cleanup pass is claimed.

### CodeRabbit findings

The five earlier actionable comments were checked against the current source:

1. Approval is reserved when queued and consumed atomically with the worker's `QUEUED → STARTING` transition and its audit event.
2. Failed approval/evidence revalidation has an audited terminal `QUEUED → FAILED` transition before process creation.
3. Secret-store load failure no longer prevents Google authentication or Dashboard startup. The replay guard is seeded conservatively when storage state is unknown; it is not seeded when no secret exists, preserving first enrollment. Step-up independently loads the secret and fails closed.
4. The QR branch exposes a cancel action; a new recovery attempt still begins with fresh Google reauthentication.
5. Successful enrollment/recovery refreshes backend session status before clearing the QR and rendering the resulting storage state.

All five previous CodeRabbit threads were replied to and resolved after the corresponding code/documentation changes. A fresh review was requested for the current PR diff; its result is not yet recorded in this report.

## CI evidence observed for the reviewed source HEAD

All listed GitHub Actions workflows completed successfully for `0413c62d10bb6309f6d764350177f6cf8df62bc3`.

| Workflow / job | Result |
|---|---|
| Backend suite | 519 passed, 9 skipped |
| Ruff | Passed — “All checks passed!” |
| Frontend unit tests | Passed |
| Playwright E2E (desktop and mobile viewports) | Passed |
| Frontend build | Passed |
| Windows Authenticator DPAPI | 17 passed |
| Windows live WinGet catalog signature/search check | 1 passed |
| Windows Auth / Session / secret storage integration | 47 passed |
| Windows job lifecycle / containment | 12 passed, 1 skipped |
| Windows WinGet adapter | Passed |

Run references:
- [CI — 43526450972](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43526450972)
- [Windows Authenticator DPAPI — 43526450886](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43526450886)
- [Windows Process Containment — 43526450990](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43526450990)
- [Windows WinGet Adapter — 43526450967](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43526450967)

The full backend suite includes OIDC, authenticator enrollment/recovery, session, Step-up, and related Auth/Session tests. Windows-specific tests were exercised on GitHub-hosted Windows runners. No claim is made that the implementer ran these tests locally.

## Residual risks and evidence not available

1. **Target Windows 11 Home acceptance is NOT VERIFIED.** Hosted Windows CI is not the user's target machine. Local acceptance must verify owner-only DACL, DPAPI round-trip, reparse-point rejection, enrollment, recovery, and Step-up.
2. **No live Google IdP ceremony** was run. OIDC tests use deterministic fakes and injected token verification.
3. **No fuzzing, penetration testing, or attack simulation** was performed.
4. **Process-local state remains single-worker only.** Sessions, OIDC transactions, Step-up challenges, and TOTP replay state are not durable/shared across multiple workers. The existing startup guard rejects unsupported multi-worker operation.
5. **Authentication audit is bounded and process-local**, not a durable compliance ledger. Before any future side-effecting capability, the project must define and enforce a mandatory durable execution audit boundary that fails closed.
6. **Windows Job Store DACL/handle gate remains separate and closed.** This PR does not authorize worker execution, WinGet, installers, or host mutation.
7. **Same-user malware / compromised Windows account remains outside the boundary.** A process running as the same user can access that user's DPAPI context and owner-only directory.
8. The loopback HTTP callback currently uses a non-Secure session cookie because the configured callback is local HTTP. This is an existing deployment assumption and must be reassessed before any non-loopback or HTTPS deployment.

## Final recommendation

**PASS WITH CONDITIONS for the P6-601 Authenticator / Session test gate.** The exact reviewed HEAD has green backend, frontend, Windows DPAPI, Windows containment, and WinGet CI evidence. The Auth/Session regression suites passed in CI.

Do not treat this report as authorization to merge. Keep PR #165 open and unmerged until:
- CodeRabbit completes its fresh review of the latest HEAD and any new actionable finding is addressed.
- Required target Windows 11 Home acceptance is completed and recorded.
- Any project-required named human A4 sign-off is obtained.
- The Product Owner explicitly decides whether to merge.

No real PC-changing capability is enabled or authorized by this review.
