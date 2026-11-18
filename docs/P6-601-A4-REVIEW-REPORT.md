# P6-601 — A4 Independent QA / Security Review Reassessment

## Review disposition

**Conclusion: CHANGES REQUIRED — runtime execution remains blocked.**

This is a read-only reassessment of the earlier A4 report against the current `main` snapshot. It distinguishes findings already remediated in code from findings that remain open or are only partially addressed. It does not authorize installer execution, worker dispatch, runtime enablement, or merge.

| Field | Value |
|---|---|
| Repository | `keng-lap/ai-agent-pc-automation` |
| Previously reviewed baseline | `310a582bcee99f4c2f90f9ac8a719a15fb88eec9` |
| Reassessed baseline | `c8ba0324174fc90779f55d5ad7fe0d29dfb01082` |
| Branch | `main` |
| Review lane | A4 — QA / Security reassessment |
| Review mode | Read-only source and design inspection |
| Live Windows 11 Home acceptance | Not performed |
| Tests executed as part of this reassessment | None |
| CI independently verified for this exact baseline | Not verified |

The reassessment compared the previous report with the current source, Windows secret-storage implementation, authentication and OIDC routes, audit schema, step-up module, Background Job Architecture addendum, P6-602 containment/status contracts, and the PR #165 security-review status document. Source inspection is not equivalent to executing tests or independently reviewing native Windows behavior.

## Executive assessment

The current product boundary remains local-first and proposal/Dry Run only. The inspected software approval API explicitly states that it has no installer dispatch, package-manager call, background-job enqueue, or machine side effect. The job-store and process-containment modules describe foundations and contracts; they do not constitute authorization to launch installers.

### Finding disposition

| ID | Severity | Current disposition | Evidence / remaining action |
|---|---|---|---|
| A4-P6-601-01 | Medium | **REMEDIATED IN MAIN** | `require_session` now raises 503 when auth services are unavailable and 401 when no valid session exists. Protected routers use this dependency. Retain route-level regression coverage. |
| A4-P6-601-02 | Medium | **IMPLEMENTED; ACCEPTANCE EVIDENCE PENDING** | Windows secret storage now uses handle-based operations, verifies current-user owner SID and protected owner-only DACL, rejects reparse points, and performs I/O through validated handles. Windows workflow and tests exist. This reassessment did not execute the Windows workflow or target-machine acceptance; do not claim the native control is independently certified. |
| A4-P6-601-03 | Medium | **OPEN — SECURITY / PRODUCT DECISION REQUIRED** | Initial TOTP enrollment still appears to authorize QR issuance using the existing application session only. The route does not show a fresh Google re-authentication or recent-authentication check, and OIDC validation checks `iat` age but not an `auth_time` freshness requirement. Decide whether to implement a narrowly scoped enrollment ceremony or explicitly accept the trusted-setup/session-theft residual risk. |
| A4-P6-601-04 | Medium | **REMEDIATED IN MAIN FOR KNOWN LAUNCH CONFIGURATIONS** | `main.py` calls `enforce_single_worker()` and rejects known multi-worker environment/CLI settings. Security state remains process-local; shared multi-worker support is still unsupported and must remain so. |
| A4-P6-601-05 | Medium | **PARTIALLY ADDRESSED — RUNTIME RELEASE BLOCKER REMAINS** | Background Job Architecture now contains a normative transition matrix, durable-record/transaction contract, worker lease and approval ordering, Windows Job Object containment requirements, scheduler DST/misfire semantics, and a threat-to-control-to-test matrix. P6-602 documents and code add lifecycle/store/status/containment foundations. However, the P6-602 containment document still lists the reviewed suspended-process launcher, Windows durable-store ACL adapter, crash/recovery behavior and Windows acceptance as not yet complete. No real worker/installer dispatch is authorized. |
| A4-P6-601-06 | Low | **REMEDIATED IN MAIN** | `AuthAuditReason` now includes `invalid_software_approval`, matching the denial path. Confirm the regression test remains in the relevant suite. |
| A4-P6-601-07 | Low | **REMEDIATED IN MAIN** | `step_up.py` now accurately states that the current plan API creates and consumes the challenges and documents the process-local limitation. |

## Detailed reassessment

### A4-P6-601-01 — Auth-disabled route dependency

**Disposition: REMEDIATED IN MAIN.**

The current `require_session` raises HTTP 503 when authentication services are unavailable and HTTP 401 when the session cannot be resolved. The old behavior returning `None` is no longer present. `main.py` applies the dependency to chat, plan, software-discovery and software-approval routers. The job router is separately included and must continue to enforce authentication on its own endpoints; its current status API contract explicitly requires an authenticated local session.

This finding may be closed as a source-level defect, subject to the existing disabled-auth route regression tests. This reassessment did not execute those tests.

### A4-P6-601-02 — Windows authenticator secret-file ACL and path trust

**Disposition: IMPLEMENTED; NATIVE ACCEPTANCE NOT VERIFIED.**

The current `windows_secret_storage.py` is materially different from the old path-based implementation. It opens path components with reparse-point-aware flags, verifies the current-user owner SID, applies and verifies a protected DACL with one owner allow ACE, rejects path-redirection reparse points, and performs reads/writes through validated handles. The authenticator store delegates Windows operations to this adapter.

A dedicated Windows Authenticator DPAPI workflow and Windows tests are present. The PR #165 review-status document correctly says these controls still require Windows CI evidence and target Windows 11 Home acceptance; that document is not itself a sign-off. This reassessment did not retrieve a successful run for the exact reassessed main SHA or perform target-machine testing. Keep the status as implemented but not independently accepted.

### A4-P6-601-03 — Initial authenticator enrollment freshness

**Disposition: OPEN.**

The current `begin_authenticator_enrollment` route calls `require_session`, checks storage/enrollment state, and then returns one-time QR material. The route does not show a fresh Google re-authentication ceremony or a recent-authentication grant. The current OIDC token validation enforces an `iat` age bound but does not validate an `auth_time` claim or require a fresh authentication event.

A still-valid stolen application session can therefore remain a concern before the owner has enrolled TOTP. The one-time QR, owner/session binding, expiry, attempt limits and TOTP confirmation reduce other risks but do not prove recent Google authentication.

The PR #165 security-review status document explicitly narrowed scope to existing Google sign-in/session and one-time TOTP enrollment, and removed recovery/replacement/WebAuthn work. That scope decision does not itself resolve this finding. Do not reintroduce recovery or replacement features as part of this finding. The Product Owner must either approve a bounded fresh-auth enrollment design or explicitly accept and document the trusted-setup residual risk before claiming this control is closed.

### A4-P6-601-04 — Process-local state and multi-worker deployment

**Disposition: REMEDIATED FOR CURRENT SUPPORTED DEPLOYMENT.**

The current app invokes `enforce_single_worker()` during app creation. It rejects known multi-worker settings from `WEB_CONCURRENCY`, `UVICORN_WORKERS`, `GUNICORN_WORKERS`, `GUNICORN_CMD_ARGS`, and parsed worker CLI arguments. The implementation explains that multi-worker mode is unsupported while security state remains process-local.

This closes the earlier missing startup guard for the configurations inspected. It does not make the state shared or safe for multi-worker deployment. Any launch mechanism not covered by the guard must be documented and tested before use.

### A4-P6-601-05 — Background Job architecture and execution contract

**Disposition: DESIGN SUBSTANTIALLY EXPANDED; IMPLEMENTATION / ACCEPTANCE GATES REMAIN.**

The current Background Job Architecture includes:
- A normative permitted-transition matrix and explicit forbidden transitions.
- Atomic queue reservation and worker-claim/approval-consumption ordering.
- Versioned durable-record fields, transaction boundaries and worker lease metadata.
- Windows Job Object containment, suspended process assignment, process identity persistence, descendant termination and UNKNOWN handling.
- Scheduler timezone, DST gap/fold, misfire and overlap semantics.
- Threat-to-control-to-test release requirements, including crash injection and duplicate-claim cases.

P6-602 adds lifecycle, SQLite operational history, read-only status API and a Windows Job Object wrapper. However, the P6-602 containment foundation explicitly leaves important gates incomplete: a reviewed suspended-process launcher, Windows durable-store DACL/owner/reparse/handle protections, crash/recovery and orphan reconciliation, and Windows acceptance tests. The job-store implementation itself documents Windows as unavailable until its native storage adapter is implemented and independently reviewed.

Therefore, the original finding that the architecture lacked a normative contract is substantially addressed, but **P6-601 architecture/runtime acceptance has not passed**. No code in this reassessment authorizes a worker, WinGet invocation, installer launch, arbitrary process, or host mutation. Keep runtime dispatch disabled until each capability-specific implementation and review gate passes.

### A4-P6-601-06 — Invalid software-approval audit reason

**Disposition: REMEDIATED IN MAIN.**

The current `AuthAuditReason` literal includes `invalid_software_approval`, which matches the denial path in `software_approval_api.py`. The original schema mismatch is no longer present in source. The regression test must remain enabled and pass in CI before this is treated as test-verified.

### A4-P6-601-07 — Stale step-up module documentation

**Disposition: REMEDIATED IN MAIN.**

The current `step_up.py` module docstring says the plan API creates and consumes challenges and accurately states the process-local limitation. The earlier statement that the challenge store was not wired to the plan route is gone.

## Current security boundary

- Google OIDC remains the primary sign-in mechanism for the local Master User.
- TOTP enrollment and exact-action Step-up remain the second-factor controls; no recovery/replacement or alternate-factor bypass is included.
- Sessions, OIDC transactions, TOTP replay state, Step-up challenges and related in-memory approval/evidence state remain process-local.
- Multi-worker deployment remains unsupported.
- Software approval remains proposal/Dry Run only.
- Job history/status foundations do not authorize job execution.
- No real WinGet invocation, installer execution, arbitrary shell/script execution, LAN/public control, or live PC mutation is authorized.

## Test and evidence statement

This reassessment did not run pytest, Ruff, frontend tests, Windows DPAPI/ACL tests, process-containment tests, or live Windows acceptance. The presence of test files and workflow definitions is not a test pass. CI for the exact reassessed main SHA `c8ba0324174fc90779f55d5ad7fe0d29dfb01082` was not independently verified in this review.

Before closing the remaining gates:
1. Resolve A4-P6-601-03 through a bounded design and explicit Product Owner disposition.
2. Obtain successful Windows CI evidence for authenticator storage and process-containment workflows on the exact relevant code head.
3. Complete the Windows durable job-store security adapter and reviewed suspended-process launcher before any worker dispatch.
4. Execute focused tests, full relevant backend tests and Ruff; preserve exact command output and CI run links.
5. Obtain an independent A4 review of the exact remediation diff and Windows evidence.
6. Keep installer/process dispatch disabled until the capability-specific A4 review and separate Product Owner enablement decision pass.

## Final gate

**A4 reassessment: CHANGES REQUIRED.** Findings 01, 04, 06 and 07 are remediated in current source; finding 02 is implemented but lacks verified native acceptance evidence; finding 03 remains open; finding 05 is substantially improved at design level but has incomplete implementation and Windows acceptance gates.

**P6-601 architecture/runtime acceptance: NOT PASSED.** This report does not authorize execution, enablement, or merge.
