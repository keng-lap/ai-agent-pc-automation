# PR #165 — P6-601 Authenticator / Session Security Review

## Review identity and limits

**Disposition: PASS WITH CONDITIONS — this report is not merge approval.**

This is ChatGPT's secondary, static A4-style security review. CodeRabbit remains the primary automated PR reviewer. This report is not a named human A4 sign-off, penetration test, or Product Owner approval.

| Field | Value |
|---|---|
| Repository | `keng-lap/ai-agent-pc-automation` |
| Pull request | [#165](https://github.com/keng-lap/ai-agent-pc-automation/pull/165) |
| Reviewed source HEAD | `5fb7cf1ab1900d3056e2e382a129a470bf88e722` |
| Base SHA | `96e4d0dc5ad6d920438056e33909d615937934fd` |
| Review date | 2026-11-14 |
| Scope | Google OIDC, sessions, TOTP, Step-up, enrollment/recovery, Windows DPAPI secret storage, software-approval confirmation, configuration path boundary, frontend, tests, lifecycle and P6-601 documentation |
| Method | Static source/diff review and inspection of GitHub Actions results for the exact source HEAD. No local tests or live Windows operations were performed. |

## Executive assessment

Google OIDC remains the primary sign-in mechanism; TOTP is used only for Step-up. The reviewed confirmation paths use a current-secret loader inside the replay-guard critical section. Recovery commits the replacement and replay step under the same guard, preventing a Step-up request from verifying against a stale secret snapshot after replacement completes.

The reviewed paths do not introduce arbitrary shell/PowerShell/CMD/script execution, dynamic handler selection, installer invocation, worker dispatch, or host mutation. Software approval remains an approval-only flow; it does not execute an installer.

No Critical or High vulnerability was verified in this static review. The remaining conditions are target-machine acceptance, a live Google identity-provider ceremony, a fresh CodeRabbit result for this exact HEAD, and any required named human A4 sign-off.

## Findings and remediation status

### F-01 — Medium — TOTP replay across Recovery and Step-up

**Status: Addressed in the reviewed source; concurrency behavior covered by regression tests.**

`StepUpChallengeStore.verify_and_consume()` accepts a `secret_loader` callback and invokes it while the shared `TotpReplayGuard` lock is held. Both the plan-approval API and software-approval API now load the active secret through this callback rather than passing a secret snapshot read before the lock. Recovery performs secret replacement and advances the owner's replay step through `consume_step_after()` under that same lock.

This serializes secret selection, TOTP verification, replay-step consumption, and recovery replacement. If Step-up obtains the lock first, its verification is committed before recovery can replace the secret. If recovery obtains it first, the subsequent Step-up loads the replacement secret. The regression suite verifies the loader executes under the replay lock and that a replaced secret cannot authorize a later step.

### F-02 — Medium — DACL mutation of an arbitrary/shared parent directory

**Status: Addressed.**

`validate_authenticator_secret_path()` restricts the secret file to a direct child of the dedicated application-owned `.agent-state/authenticator` directory. Validation occurs in environment configuration and `build_auth_services()`, so directly constructed Settings cannot bypass the boundary. The Windows adapter does not apply its directory DACL to an arbitrary configured/shared parent.

Existing reparse-point and owner-SID checks remain in place. Existing files are opened through verified handles; an existing wrong-owner file is rejected rather than taken over.

### F-03 — Low — Session rotation failure after secret persistence

**Status: Addressed.**

If the secret has been persisted but session rotation returns `None`, the endpoint records and reports the authenticator change as successful rather than returning a misleading authentication failure. No replacement cookie is issued; the owner may need to sign in again. A regression test verifies persisted secret state and the success audit event when rotation fails.

### F-04 — Low — Temporary or partial secret-file residue after DACL setup failure

**Status: Addressed; filesystem cleanup remains best-effort.**

`_open_file()` records successful `CREATE_NEW` creation immediately after `CreateFile` returns and before the DACL operation can fail. On a later setup failure, it closes the new handle and removes only the file created by that attempt. A Windows regression test forces DACL setup to fail and asserts the new file is removed.

Failed replacement attempts also attempt to remove their randomly named temporary file while the verified parent directory remains pinned. If the filesystem refuses cleanup, inert DPAPI ciphertext may remain in the owner-only directory; no general-purpose cleanup pass is claimed.

### F-05 — Low — Enrollment / Recovery confirmation route and audit classification

**Status: Addressed.**

The API passes the confirmation route's expected mode into `AuthenticatorEnrollmentManager.confirm()`. A pending recovery cannot be confirmed through the enrollment route, and a pending enrollment cannot be confirmed through the recovery route. A mismatch is rejected before secret persistence or replay-step consumption. Regression coverage exercises both mismatch directions, verifies the pending setup remains available, and then confirms through the correct route.

The audit event records the endpoint that was actually attempted; a mismatched route is recorded as a denied attempt, never as a successful operation of the other type.

### F-06 — Low — Background-job lifecycle contract consistency

**Status: Addressed in documentation.**

The transition matrix now states that `QUEUED → STARTING` creates a valid unexpired lease atomically with the claim, and that `QUEUED → CANCELLED` releases the reserved approval and commits the cancellation audit atomically. It also includes `CANCEL_REQUESTED → VERIFYING` when process-tree completion is proven, while retaining the existing terminal `CANCELLED` and uncertain `UNKNOWN` paths.

### OIDC freshness boundary

Google's supported authorization prompt values include `select_account`, `consent`, and `none`; the implementation does not rely on unsupported `prompt=login` or `max_age=0` behavior. For the dedicated enrollment/recovery OIDC transaction, the client requests the essential `auth_time` ID-token claim and rejects missing, stale, future, or malformed values. The resulting application session receives a five-minute, one-use fresh-authentication grant.

`select_account` is used only for account selection and is not treated as proof of freshness. If Google's last authentication time is stale, the owner must complete a fresh Google sign-in outside the app and retry. The provider setup document records that the Google project must enable the claim and satisfy Google's app-verification prerequisite. See [Google OpenID Connect claims](https://developers.google.com/identity/openid-connect/openid-connect) and [Google's session metadata announcement (2026-06-16)](https://developers.googleblog.com/enhance-security-and-trust-new-session-metadata-in-sign-in-with-google/).

**Live Google IdP reauthentication is NOT VERIFIED.** Deterministic tests verify transaction purpose propagation through `complete_login()`, claim validation, and one-time consumption of the session grant; they do not prove the live Google project is configured or verified correctly.

### Additional regression and CI-trigger checks

- The Windows workflow path filters include `auth_api.py` and `test_auth_api.py`, so authentication API changes trigger the relevant Windows integration tests.
- The DACL repair test opens the file directly with `READ_CONTROL` and verifies the resulting owner-only DACL without invoking the repair routine a second time.
- The OIDC regression test exercises recent-authentication purpose from transaction creation through `complete_login()` and confirms that the session grant can be consumed exactly once.
- The software-approval confirmation path now obtains the current TOTP secret under the replay guard instead of loading it before verification.

## CI evidence for the reviewed source HEAD

All listed GitHub Actions workflows completed successfully for `5fb7cf1ab1900d3056e2e382a129a470bf88e722`.

| Workflow / job | Result |
|---|---|
| Backend suite | 531 passed, 11 skipped |
| AI reviewer unit tests | 13 passed |
| Ruff | Passed — “All checks passed!” |
| Frontend unit tests | 42 passed |
| Playwright E2E (desktop and mobile viewports) | 19 passed |
| Frontend build | Passed |
| Windows Authenticator DPAPI | 21 passed |
| Windows live WinGet catalog signature/search check | 1 passed |
| Windows authenticator storage / DPAPI integration | 55 passed |
| Windows job lifecycle / containment | 13 passed, 1 skipped |
| Windows WinGet adapter | 15 passed |

Run references:
- [CI — 43554562939](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43554562939)
- [Windows Authenticator DPAPI — 43554562963](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43554562963)
- [Windows Process Containment — 43554563067](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43554563067)
- [Windows WinGet Adapter — 43554562925](https://github.com/keng-lap/ai-agent-pc-automation/actions/runs/43554562925)

These results are GitHub-hosted CI evidence. No claim is made that tests were run locally by the reviewer.

## Residual risks and evidence not available

1. **Target Windows 11 Home acceptance is NOT VERIFIED.** Hosted Windows CI does not replace acceptance on the user's target machine. Local acceptance must verify owner-only DACL, DPAPI round-trip, reparse-point rejection, enrollment, recovery, and Step-up.
2. **No live Google IdP ceremony** was run. OIDC tests use deterministic fakes and injected token verification.
3. **No fuzzing, penetration testing, or attack simulation** was performed.
4. **Process-local state remains single-worker only.** Sessions, OIDC transactions, Step-up challenges, and TOTP replay state are not durable/shared across multiple workers. Unsupported multi-worker operation remains guarded.
5. **Authentication audit is bounded and process-local**, not a durable compliance ledger. Before any future side-effecting capability, the project must define and enforce a mandatory durable execution-audit boundary that fails closed.
6. **Windows Job Store DACL/handle gate remains separate and closed.** This PR does not authorize worker execution, WinGet installation, installers, or host mutation.
7. **Same-user malware / compromised Windows account remains outside the boundary.** A process running as the same user can access that user's DPAPI context and owner-only directory.
8. The loopback HTTP callback currently uses a non-Secure session cookie because the configured callback is local HTTP. This existing deployment assumption must be reassessed before any non-loopback or HTTPS deployment.

## Final recommendation

**PASS WITH CONDITIONS for the P6-601 Authenticator / Session test gate.** Backend, Ruff, frontend, Windows DPAPI, Windows containment, and WinGet CI are green on the reviewed source HEAD.

A fresh full CodeRabbit review has been requested for this exact HEAD; its result must be checked before treating automated review as complete. Keep PR #165 open and unmerged until:
- CodeRabbit completes its fresh review and any new actionable finding is addressed.
- Required target Windows 11 Home acceptance is completed and recorded.
- Any project-required named human A4 sign-off is obtained.
- The Product Owner explicitly decides whether to merge.

No real PC-changing capability is enabled or authorized by this review.
