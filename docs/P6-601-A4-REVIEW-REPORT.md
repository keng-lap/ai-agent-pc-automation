# P6-601 — A4 Independent QA / Security Review Report

## Review disposition

**Conclusion: CHANGES REQUIRED.**

The read-only review is complete for the exact source snapshot below. The current implementation remains Dry Run / proposal-only and no current code path reviewed here launches WinGet or an installer. This report does not authorize execution, runtime enablement, or merge.

| Field | Value |
|---|---|
| Repository | `keng-lap/ai-agent-pc-automation` |
| Exact reviewed baseline | `310a582bcee99f4c2f90f9ac8a719a15fb88eec9` |
| Branch | `main` |
| Review lane | A4 — QA / Security |
| Review mode | Read-only source and design review |
| Live Windows inspection | Not performed |
| Tests executed by reviewer | None |
| CI evidence independently re-run/verified for this review | None |

The review inspected the Phase 6 baseline, A4 packet, source map, Trusted Software Discovery and Background Job Architecture documents; current OIDC/session, DPAPI/TOTP, step-up, plan, policy, dispatch, audit, middleware and app-composition code; the current software discovery/evidence/approval boundary; and selected related backend tests. File inspection is not equivalent to executing those tests.

## Executive assessment

### Controls that are present

- Google authorization-code flow uses PKCE S256, one-time server-side state/nonce, a fixed loopback redirect, bounded token exchange, ID-token signature verification through Google Auth, issuer/audience/authorized-party checks, nonce, expiry/issued-at, verified email and a stable Google `sub` allowlist.
- Application sessions use high-entropy bearer tokens, retain only token digests, enforce absolute expiry with monotonic deadlines, support revocation, and are explicitly process-local.
- TOTP uses a 160-bit secret, six digits, 30-second steps, a bounded ±1-step window, constant-time code comparison and a thread-safe one-use-per-step replay guard.
- Step-up challenges bind owner, session, plan ID, action digest and server-derived risk; challenges are short-lived, one-use, bounded and rate-limited.
- Plan approval now authenticates before returning a cached Dry Run result. A cached result is not a reusable execution grant.
- Tool catalog, policy and handler dispatch are backend-owned and fixed. Current handlers only return Dry Run results.
- Authenticator secret bytes are protected using current-user Windows DPAPI. The DPAPI cleanup path now frees both returned data and description allocations.
- Software evidence is minted only from backend discovery/staging facts. Publisher signer trust anchors default-deny; an unconfigured trust anchor prevents evidence registration.
- The exact-artifact adapter prepares a local manifest from approval-bound evidence and locks the prepared files against write/delete while the lock context is held. It does not invoke WinGet.

### Findings requiring remediation or explicit disposition

| ID | Severity | Area | Finding |
|---|---|---|---|
| A4-P6-601-01 | Medium | Auth-disabled route dependencies | `require_session` returns `None` when auth services are absent. Router-level `Depends(require_session)` therefore does not enforce authentication in auth-disabled mode. The current software-approval API has its own explicit auth-service/principal check and no installer dispatch exists, so this is not evidence of a current install-approval bypass. However, plan and discovery routes are reachable without an application session, contrary to the Phase 6 fail-closed rule; future routes could mistakenly rely only on the dependency. |
| A4-P6-601-02 | Medium | Windows DPAPI secret-file storage | `EncryptedTotpSecretFileStore` uses `Path.is_symlink()` checks and `os.open(..., O_CREAT | O_EXCL, 0o600)`, but does not establish/verify a restrictive Windows DACL, owner SID, trusted parent directory or handle-based reparse-point policy. POSIX mode `0o600` is not proof of a Windows ACL. DPAPI protects secret confidentiality, but permissive path/ACL handling can still permit replacement/deletion (availability/integrity) and path-race risks. |
| A4-P6-601-03 | Medium | Authenticator enrollment ceremony | A valid application session can start initial TOTP enrollment without a fresh Google re-authentication or other recent-authentication check. The QR is one-time and confirmation proves possession of the newly generated TOTP secret, but a stolen still-valid session could enroll an attacker-controlled factor before the owner has enrolled one. Require a narrowly scoped recent-authentication ceremony before initial enrollment, or document and approve a compensating trusted-setup assumption. |
| A4-P6-601-04 | Medium | Process-local security state | Session, OIDC transaction, TOTP replay, step-up challenge, plan, approval-cache and evidence-registry state are process-local. The docs disclose this, but application startup/deployment does not enforce a single worker. Multiple workers can split login/challenge state and do not share TOTP replay consumption. Until shared atomic storage exists, reject unsupported multi-worker configuration and test the guard. |
| A4-P6-601-05 | Medium | Background Job architecture | The architecture describes the right high-level controls, but is not yet an implementable execution contract: it lacks a normative transition table with allowed/forbidden edges, durable schema and transaction boundaries, atomic approval-consumption/job-creation/worker-claim ordering, lease ownership rules, and a concrete Windows process-tree containment contract (for example, Job Object ownership and descendant/orphan handling). Scheduler DST/misfire/overlap semantics are required but not fully decided. Do not begin runtime execution work from this document alone. |
| A4-P6-601-06 | Low | Authentication audit schema | `software_approval_api.py` records denial reason `invalid_software_approval`, but that value is absent from the `AuthAuditReason` Literal in `auth_audit.py`. Pydantic validation therefore fails and `record_auth_audit_event` silently returns `False`; the denial event is dropped. Add the reason to the schema or use an existing valid reason and add a regression test. |
| A4-P6-601-07 | Low | Step-up documentation | The module docstring in `step_up.py` says the challenge store is not wired to the P1 route, while `auth_api.py` constructs the store and `plan_api.py` creates and consumes challenges. Update the stale description so future reviewers do not infer the wrong trust boundary. |

## Detailed findings

### A4-P6-601-01 — Router dependency is not an authentication gate when auth is disabled

**Affected code:** `src/backend/agent_backend/auth_api.py` — `require_session`; `src/backend/agent_backend/main.py` — `create_app` router dependencies; `software_discovery_api.py`; `plan_api.py`.

When `request.app.state.auth_services` is `None`, `require_session` returns `None` rather than rejecting the request. `main.py` installs this function as a dependency for the plan, software-discovery and software-approval routers. The dependency therefore behaves as an authentication bypass in the no-auth configuration.

The software-approval endpoints additionally call `_authenticated_context`, which rejects missing services/principal; this review found no current installer dispatch. The defect is that other protected routes (including read-only plan and discovery operations) are not actually protected, and the common dependency is unsafe as a future side-effect gate.

**Required remediation:**
1. Separate intentionally public routes (health, login start/callback, unauthenticated session-status response) from authenticated routers.
2. Make the authenticated dependency raise 401/503 when authentication is disabled for routes that require it; do not use `None` as a successful dependency result.
3. Add tests with auth disabled for every protected route, including plan read/create, discovery, software approval and all future job endpoints.
4. Keep the internal exact-approval check as defense in depth.

**Current impact:** no real install execution was found. This remains a policy and future execution release blocker.

### A4-P6-601-02 — Windows secret-file ACL and path trust are not established

**Affected code:** `src/backend/agent_backend/authenticator.py` — `EncryptedTotpSecretFileStore.save/load/is_configured`.

The file store performs a pre-open symlink check and creates parent directories automatically. It relies on `0o600` at file creation, which does not establish a restrictive Windows DACL. It also does not validate the owner/effective DACL through the same open handle or establish that the parent path is trusted and free of reparse-point redirection.

DPAPI current-user protection reduces the confidentiality impact of reading the ciphertext, but does not prevent a process/user with path write access from deleting or replacing the file and causing authentication denial or integrity loss.

**Required remediation:** implement a Windows-specific handle-based open/validation strategy; reject reparse points/races; verify owner SID and protected DACL for the current Windows user; require a trusted parent path without recursively changing arbitrary parent ACLs; perform I/O through the validated handle. Add Windows CI tests for effective ACLs, owner, symlink/reparse rejection and race resistance. Do not treat POSIX mode bits as Windows security evidence.

### A4-P6-601-03 — Initial authenticator enrollment lacks recent re-authentication

**Affected code:** `src/backend/agent_backend/auth_api.py` — `begin_authenticator_enrollment`; `authenticator.py` — `AuthenticatorEnrollmentManager.begin/confirm`.

The enrollment manager correctly binds a pending enrollment to the authenticated owner, invalidates an older pending QR, expires it, limits failed attempts, consumes a TOTP step and stores the secret only after successful confirmation. However, the HTTP route authorizes enrollment using only the existing application session. There is no recent Google re-authentication or equivalent step-up before establishing the first factor.

**Threat precondition:** an attacker obtains a still-valid owner session before TOTP has been enrolled.

**Impact:** the attacker can establish the authenticator factor used for subsequent step-up operations, subject to the victim not already having an enrolled secret.

**Required remediation:** require a fresh OIDC re-authentication (with a one-time, session-bound enrollment transaction) before returning enrollment QR material. Rotate the application session after successful enrollment. If the project intentionally accepts this residual for a physically trusted first-run setup, record the explicit threat assumption and Product Owner acceptance; do not silently call the current route phishing-resistant or resistant to session theft.

### A4-P6-601-04 — Process-local state is documented but multi-worker mode is not rejected

**Affected code:** `oidc.py`, `step_up.py`, `totp.py`, `plans.py`, `plan_api.py`, `software_evidence.py`, `main.py` and deployment configuration.

The code correctly uses locks within one process and the docs state that the state is process-local. That is not equivalent to cross-process atomicity. Multiple workers would each have independent sessions, pending OIDC state, TOTP replay history, challenges, plans, approvals and evidence.

A request routed to a different worker can fail unexpectedly; more importantly, separate workers do not share the one-use TOTP replay guard. The current architecture cannot claim replay protection across workers.

**Required remediation:** until shared durable atomic state is implemented and reviewed, enforce one worker at startup/launcher configuration and document the supported invocation. Add a negative test proving unsupported worker counts/configurations are rejected. Before multi-worker support, use shared atomic consume semantics for TOTP replay, challenge consumption, approval consumption and job claiming.

### A4-P6-601-05 — Background Job design needs a normative state/persistence/process contract

**Affected document:** `docs/P6-601-BACKGROUND-JOB-ARCHITECTURE.md`.

The document correctly prohibits arbitrary scripts, shell steps, automatic elevation, automatic retries of ambiguous jobs, and success based only on exit code. It also correctly requires per-run approval for side effects and UNKNOWN state for ambiguous recovery.

Before implementation, the following must be normative rather than left as prose:
- Full transition matrix, including actor, preconditions, atomic state mutation and forbidden transitions.
- Job Definition/Run/evidence/approval/worker-lease schema, versioning, integrity, ACL and retention/deletion rules.
- Transaction order for consuming approval, creating a job, claiming a job and recording execution-start; crash injection at every boundary must not permit duplicate execution.
- Worker lease ownership, stale-lease recovery and proof of process identity.
- Windows process containment and descendant lifecycle, including process-tree termination, orphan detection and UNKNOWN semantics.
- Scheduler timezone/DST/misfire/overlap behavior and bounded catch-up rules.
- Exact relationship between operational job history and the separate mandatory fail-closed security audit ledger.

**Required remediation:** add a design addendum and threat-to-control-to-test matrix before runtime implementation is proposed. This is a design blocker, not a claim that a worker currently exists.

### A4-P6-601-06 — Invalid software-approval audit reason is silently discarded

**Affected code:** `src/backend/agent_backend/software_approval_api.py` — denial event; `src/backend/agent_backend/auth_audit.py` — `AuthAuditReason` and `record_auth_audit_event`.

The denial path passes `invalid_software_approval`, which is not an allowed `AuthAuditReason`. The event model rejects it; the wrapper catches the validation error and returns `False`. The API response is still denied, but the intended audit record is lost without surfacing an error.

**Required remediation:** add the literal or use an existing semantically correct reason. Add a test asserting the event appears in the sink for that denial path. This optional sink remains diagnostic only and must not be treated as the mandatory execution ledger.

### A4-P6-601-07 — Stale step-up module documentation

**Affected code:** `src/backend/agent_backend/step_up.py` module docstring.

The code is wired through `build_auth_services` and the plan API; the docstring still says it is not wired to the P1 route. This is documentation drift. Update it and retain the explicit single-process limitation.

## Explicit dispositions of the review packet questions

| Review topic | A4 disposition |
|---|---|
| OIDC PKCE/state/nonce/signature/issuer/audience/expiry/allowlist | Controls are present in the inspected code. No live Google round-trip or independent token-signature test was run in this review. |
| Session token entropy/digest/TTL/revocation | Present. Process-local and restart-invalidated by design. |
| DPAPI protection and native allocation cleanup | DPAPI current-user protection and both output-buffer cleanup paths are present. Windows ACL/path hardening remains a finding. |
| TOTP profile, skew, constant-time comparison and replay | RFC-style 6-digit/30-second HMAC-SHA1 implementation, ±1 step, constant-time compare and per-owner replay guard are present. Replay state is process-local; multi-worker use is unsupported. |
| Step-up exact-action binding, expiry, attempts and replay | Owner/session/plan/digest/risk binding and one-time consumption are present. Stale module docstring is recorded above. |
| Auth-disabled route behavior | Router dependency is not fail-closed when auth services are absent; see A4-P6-601-01. Current software approval has a second internal guard. |
| Approval cache/idempotency | Current cache is Dry Run response idempotency only and is checked after fresh step-up verification. It is not an execution authorization primitive. |
| Audit fail-open behavior | Current auth/security sinks are bounded process-local optional diagnostics. Acceptable only for the current non-side-effecting boundary; insufficient for any side effect. |
| Trusted Software Discovery / TOCTOU | Discovery is explicitly conditional; staged binary evidence and signer fingerprint are bound into evidence/approval. Publisher trust anchors default-deny. Exact manifest lock must remain held throughout any future WinGet read/execute interval. No install path is enabled. |
| Background Job architecture | High-level safety intent is sound; normative transition, persistence/transaction and Windows process-containment details remain incomplete; see A4-P6-601-05. |
| Loopback HTTP cookie with `Secure=False` | Accepted only under the documented loopback-only HTTP deployment with strict Host/Origin and local-token checks. It does not protect against same-user malware, browser compromise or a compromised local process. Do not expose the service to LAN/public interfaces. |

## Threat-to-control-to-test traceability

| Threat | Existing control | Evidence reviewed | Remaining test/remediation |
|---|---|---|---|
| OIDC login CSRF/replay | One-time state and nonce; PKCE S256 | `oidc.py`, `test_oidc.py` | Execute full suite; test callback concurrency and malformed provider responses |
| Wrong Google account | Stable `sub` allowlist | `oidc.py`, `auth_api.py` | Test live configured owner flow; no live test performed |
| Session theft/replay | High-entropy token, digest storage, expiry, revoke, HttpOnly/SameSite cookie | `oidc.py`, `auth_api.py` | Add recent-auth enrollment ceremony; document local-process threat |
| TOTP replay | Per-owner monotonic-step guard | `totp.py`, `step_up.py`, tests | Enforce one worker or shared atomic storage; execute concurrency tests |
| Action/parameter substitution | Plan digest + owner/session/action/risk-bound challenge | `plans.py`, `step_up.py`, `plan_api.py` | Execute negative and concurrency tests; preserve new execution-specific state machine |
| Auth disabled | Router dependency plus internal approval check | `main.py`, `auth_api.py`, `software_approval_api.py` | Fix dependency behavior and test every protected route |
| Secret-file disclosure/tamper/DoS | Current-user DPAPI encryption | `authenticator.py`, selected tests | Windows ACL, handle/reparse and race tests |
| Audit loss | Strict allowlist, bounded optional sinks | `audit.py`, `auth_audit.py`, approval API | Fix invalid reason; implement separate mandatory durable ledger before side effects |
| Manifest/evidence substitution | Exact hashes, source commit, approval digest, signer fingerprint, default-deny anchor | discovery/evidence/approval/adapter modules | Keep manifest lock across entire future execution; add Windows acceptance evidence |
| Duplicate/ambiguous jobs | Architecture requires idempotency and UNKNOWN state | Background Job Architecture document | Normative atomic state machine, persistence schema, process containment and crash-injection tests |

## Test and evidence statement

The reviewer did **not** execute pytest, Ruff, frontend tests, Windows DPAPI tests, WinTrust/signature tests, or live Windows acceptance tests. The reviewer did not independently verify GitHub Actions results for the reviewed main SHA. The existence of test files or prior PR CI records is not represented here as a test pass.

Required before closing the findings:
1. Add focused regression tests for A4-P6-601-01, A4-P6-601-03, A4-P6-601-04 and A4-P6-601-06.
2. Run backend tests and Ruff on the remediation head; verify import ordering before reporting CI green.
3. Run Windows-specific DPAPI, ACL, reparse-point and process-boundary tests on Windows CI.
4. Independently review the remediation diff and exact test evidence.
5. Keep all installer/process dispatch disabled until the separate capability-specific A4 review and Product Owner enablement decision.

## Final gate

**P6-601 A4 review: completed with CHANGES REQUIRED.**

**P6-601 architecture acceptance: not yet passed.** The current runtime remains Dry Run / proposal-only. No WinGet invocation, installer execution, background worker, job dispatch, or live PC mutation is authorized by this report.

The Product Owner must explicitly disposition the Medium findings before any side-effecting runtime task is started. Low findings should also be corrected in the same bounded remediation work where practical. This report does not approve a PR or authorize merge.
