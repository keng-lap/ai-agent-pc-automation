# P6-609-B — Execution Security Foundation

## Status and authority

**Status: design contract only.** This document decomposes P6-609-B into reviewable implementation slices. It does not authorize installer execution, change Phase 5 policy, enable a worker, or alter the Windows host.

- Task / milestone: P6-609-B under P6-609 General Software Installation.
- Governing decisions: `docs/P6-609-GENERAL-SOFTWARE-INSTALLATION.md`, `docs/P6-609-A-ARCHITECTURE-RECONCILIATION.md`, and the existing Phase 5 Dry Run policy.
- Product Owner direction: general installation planning and capability design authorized; real execution remains separately gated.
- Non-goals: package-manager invocation, downloads, installer execution, real-install policy enablement, Windows privilege elevation, remote execution, and Phase 6 scope expansion.
- Security design and runtime tests: not applicable to this documentation-only change. No runtime code is changed. Markdown validation and CI status must be recorded separately; no runtime test result is claimed here.

## 1. Existing baseline and constraints

The source inspection of current `main` establishes the following:

| Area | Existing primitive | Gap this milestone must close |
|---|---|---|
| Exact proposal | `InstallApprovalBinding` hashes plan digest and immutable verified package evidence | The binding is retained in process-local dictionaries, not a durable approval ledger |
| Step-up | `StepUpChallengeStore` binds owner, session, plan, action digest, expiry and one-use TOTP proof | Challenge and TOTP replay state are process-local; restart / multi-process atomicity is not provided |
| Job persistence | `SQLiteJobStore` persists job metadata, events, versions and owner-scoped idempotency | Job creation is not atomically coupled to approval consumption or mandatory execution audit |
| Lifecycle | Job state machine and worker lease primitives exist | Durable worker claim / lease / approval reservation integration is incomplete |
| Audit | `AuditEventSink` is bounded and process-local; optional recording intentionally cannot block safe paths | It is not a durable, mandatory side-effect ledger |
| Platform storage | Job store delegates database path protection to a platform adapter | Current source documents Linux as the only enabled platform; Windows remains fail-closed |

The current software-approval API intentionally returns `APPROVED_NOT_EXECUTED`. Preserve that behavior until all implementation, review, CI, Windows acceptance, and explicit enablement gates have passed.

## 2. Core invariants

These are release-blocking invariants, not implementation suggestions.

1. **One exact approval, at most one job reservation.** An approval is bound to one owner, authenticated session, plan identifier, action digest, package evidence digest, privilege scope, and expiry.
2. **No substitution.** Any change to package ID, version, publisher, source, manifest commit/hash, installer hash/URL, signer identity, architecture, scope, or action invalidates the approval and requires a new review and approval.
3. **Atomic reservation.** Durable approval consumption, creation of the single job, the initial job event, the audit event `approval.reserved`, and the worker-claim eligibility transition commit in one database transaction.
4. **No response-cache authority.** An HTTP success response, repeated request, stale in-memory object, client job ID, or idempotency key by itself never authorizes execution. The worker must load and validate the durable unconsumed/reserved record.
5. **At-most-once dispatch boundary.** Only one worker can atomically claim a queued reserved job. A lease expiry does not prove that no installer process started.
6. **Audit is mandatory.** If the durable audit row cannot be committed in the same transaction as the state change, the state change rolls back and dispatch is blocked. Optional diagnostic sinks remain separate.
7. **No blind replay after restart.** A job found in STARTING/RUNNING or with a process-start intent but no conclusive process outcome is reconciled to a proven state or `UNKNOWN`; it is never automatically returned to QUEUED.
8. **Fail closed on platform protection.** If the SQLite database, WAL/SHM files, parent directory, ACL/DPAPI protection, locking, or durability guarantees cannot be verified on Windows, approval reservation and worker dispatch are unavailable.
9. **Dry Run is unchanged.** No change in this milestone weakens the Phase 5 default-deny policy or registers a side-effecting handler.
10. **No request-thread process launch.** HTTP handlers may validate and persist a proposal/reservation only. A future fixed backend-owned worker is the sole process-launch boundary.

## 3. Durable data model

Use a single protected SQLite database initially, with explicit schema migration and transaction boundaries. Do not persist TOTP secrets, raw TOTP codes, prompts, model output, arbitrary argv, raw installer output, or executable paths.

### 3.1 `install_approvals`

Suggested columns:

- `approval_id` — random opaque identifier, primary key.
- `owner_id`, `session_id`, `plan_id` — authenticated ownership/session binding.
- `action_digest`, `plan_digest`, `evidence_digest` — lowercase SHA-256 digests.
- `evidence_ref` — backend-owned durable reference to validated evidence, not a client-controlled locator.
- `status` — `APPROVED`, `RESERVED`, `CONSUMED`, `EXPIRED`, `REVOKED`.
- `approved_at`, `expires_at`, `reserved_at`, `consumed_at` — UTC timestamps.
- `job_id` — nullable until reservation; unique when set.
- `version` — optimistic concurrency counter.

Constraints:
- Unique active approval for the same exact plan/action binding.
- Unique `job_id`; one approval cannot map to multiple jobs.
- Status changes use conditional updates with expected status and version.
- Approval expiry is checked using backend time inside the transaction.
- Evidence is reloaded and revalidated before reservation; a digest match does not replace trust-anchor or freshness checks.

### 3.2 `execution_audit_events`

Append-only, bounded, privacy-minimized ledger:

- Monotonic `sequence` primary key.
- `event_id` random unique identifier.
- `occurred_at` UTC timestamp.
- `job_id`, `approval_id`, `owner_id` where applicable.
- `event_type` from a strict backend enum.
- `from_state`, `to_state`, `outcome` from strict enums.
- `action_digest` and `correlation_id`.
- `reason_code` from an allowlist; no arbitrary exception text.

Required event types include proposal recorded, approval confirmed, approval reserved, preflight denied, worker claimed, process-start intent, process attached, execution completed, verification completed, failed, partial, unknown, cancellation requested/completed, and recovery reconciled.

The ledger must not contain secrets, TOTP codes, prompt/model text, arbitrary command lines, installer stdout/stderr, or full filesystem paths. Detailed bounded diagnostics, if required, belong in a separate protected diagnostic channel and never authorize execution.

### 3.3 Job and process execution records

Extend the existing job model only through a reviewed migration. Persist:
- durable state and version;
- worker lease identity and expiry;
- process-start intent timestamp;
- Windows PID plus process creation time (PID alone is reusable);
- Job Object identity / containment metadata;
- process exit status and verification outcome as allowlisted fields;
- reconciliation status.

Do not persist arbitrary process arguments. The worker reconstructs the fixed adapter invocation from the immutable approved evidence and backend-owned adapter code.

## 4. Transaction protocols

### 4.1 Approval confirmation

The TOTP challenge, replay guard, and approval must have restart-safe, concurrency-safe semantics before this flow can produce an executable approval.

Required protocol:
1. Authenticate the current owner and session.
2. Load the exact plan and durable evidence reference; verify owner/session, digest, source trust, and expiry.
3. Verify and consume the exact-action TOTP challenge with durable one-use/replay protection.
4. In one atomic transaction, mark the approval `APPROVED`, persist the confirmation audit event, and commit.
5. Return an approval receipt that explicitly states `APPROVED_NOT_EXECUTED`.

If durable TOTP challenge/replay consumption cannot be made atomic with approval confirmation, fail closed. Do not silently fall back to the current process-local stores for a real-execution path. The existing process-local flow may remain for its current non-executing behavior until a separately reviewed migration is complete.

### 4.2 Approval reservation and job creation

This is the critical exactly-once reservation boundary:
1. Begin an immediate write transaction.
2. Reload approval by opaque ID and authenticated owner/session.
3. Require status `APPROVED`, unexpired approval, expected version, and exact plan/action/evidence digests.
4. Revalidate that the evidence reference is still current, trusted, and not revoked. If revalidation requires I/O, complete it before entering the transaction and recheck its immutable digest/version inside the transaction.
5. Insert one `QUEUED` job with a server-generated job ID and deterministic idempotency binding to this approval.
6. Conditionally update approval `APPROVED -> RESERVED`, attaching that job ID.
7. Insert the `approval.reserved` audit event and initial job event.
8. Commit. Any constraint, audit, or storage failure rolls back all writes.

A retry with the same authenticated approval may return the same existing job receipt only if the durable approval already references that exact job and digest. A different action, owner, session, or digest is a conflict. No retry creates a second job.

### 4.3 Worker claim and process-start boundary

Worker claim must be a database transaction:
1. Select only `QUEUED` jobs whose approval is `RESERVED` and whose digest/job relationship matches.
2. Atomically set `STARTING`, issue a unique lease token, and append `worker.claimed`.
3. Commit before any OS process creation.
4. Revalidate all preflight gates and write `preflight.passed` or `preflight.denied` with a mandatory audit event. A denial transitions to a terminal/non-dispatchable result.
5. Before process creation, persist `process_start_intent` and its audit event. If this transaction fails, create no process.
6. Future launcher must create suspended, assign to the Windows Job Object before resume, persist the PID plus creation time and containment identity, then resume. This launch sequence is a separate P6-609-C implementation/review gate.
7. If the process may have started but durable identity/ownership cannot be established, mark `UNKNOWN` and reconcile; never requeue automatically.

### 4.4 Completion

A worker may report process exit, but only independent package-state verification can establish success. Persist the verification result and terminal job transition with the matching mandatory audit event in one transaction. Distinguish `SUCCEEDED`, `FAILED`, `REBOOT_REQUIRED`, and `UNKNOWN`. Exit code zero alone is insufficient.

## 5. Restart and recovery rules

At startup, scan nonterminal jobs and process records under a recovery lock:
- `QUEUED` with valid `RESERVED` approval and no process-start intent may remain eligible for claim.
- `STARTING` without process-start intent may be safely failed or returned to a non-dispatchable recovery state only when the transaction history proves no launch was attempted.
- `STARTING` with process-start intent, or `RUNNING` with missing/unverifiable process identity, becomes `UNKNOWN` pending reconciliation.
- A live process is reattached only when PID, process creation time, executable identity, and Job Object membership all match the durable record.
- An exited process requires independent installed-state inspection before a terminal result.
- `UNKNOWN` is never automatically retried. Reconciliation may conclude success, failure, partial, or remain unknown; any new installation attempt requires a new approval after the actual host state is known.
- An expired worker lease is a liveness signal, not proof that no side effect occurred.

## 6. Windows storage and concurrency gate

The existing `SQLiteJobStore` is not yet a Windows-ready execution ledger. Before use for this purpose, separately prove:
- secure creation and validation of the database, parent directory, WAL and shared-memory files;
- restrictive current-user ACLs and reparse-point defenses;
- DPAPI protection only for data that requires it, with key lifecycle and recovery documented;
- SQLite WAL, FULL synchronous durability, busy handling, transaction isolation, and crash consistency on supported Windows filesystems;
- process-level concurrency across multiple backend workers;
- migration rollback and corruption behavior;
- no symlink/reparse-point substitution or database replacement between validation and use.

If any check fails, the capability remains unavailable; do not weaken path validation or fall back to an unprotected database.

## 7. Implementation slices and exit criteria

### B1 — Durable approval ledger
- Add versioned schema and repository/service boundary for approvals.
- Persist exact owner/session/plan/action/evidence digest and expiry.
- Add durable one-use TOTP challenge and replay design or explicitly keep executable reservation blocked until it exists.
- Tests: restart persistence, owner/session mismatch, changed digest, expiry, duplicate confirmation, concurrent confirmation, replayed TOTP, transaction rollback.

### B2 — Atomic approval-to-job reservation and audit
- Couple approval reservation, job creation, job event, and mandatory audit in one transaction.
- Preserve existing read-only job API; no public start/retry endpoint.
- Tests: same request returns same job; changed idempotency binding conflicts; concurrent reservation yields exactly one job; injected audit/database failure yields zero job and zero consumed approval; no request can dispatch.

### B3 — Durable worker lease and recovery protocol
- Persist lease and process-start intent with compare-and-swap state/version checks.
- Add recovery scanner that never requeues ambiguous jobs.
- Tests: competing workers, lease expiry, crash before/after process-start intent, PID reuse, missing Job Object, process still alive, UNKNOWN never auto-retries.

### B4 — Windows process containment design and implementation
- Separate reviewed suspended-process launcher; assign Job Object before resume.
- Bounded stdout/stderr drain, cancellation, timeout, descendant handling, shutdown and orphan reconciliation.
- Tests use synthetic child processes only; no package manager or installer.
- No implementation is approved to launch WinGet in this milestone.

### B5 — Independent security and platform review
- A4 review of approval, durable TOTP/replay, audit, transaction ordering, storage and worker recovery.
- CI and Windows synthetic containment tests pass.
- Windows storage security review explicitly passes.
- Real-install policy remains default-deny until a separate Product Owner decision after P6-609-C and P6-609-E gates.

## 8. Required negative guarantees

Every implementation slice must prove:
- audit unavailable => no approval reservation, job claim, or process start;
- database unavailable/corrupt/unprotected => no dispatch;
- approval expired/revoked/replayed/consumed => no new job;
- owner/session/action/evidence mismatch => no reservation;
- duplicate concurrent requests => at most one durable job;
- worker lease race => at most one claimant;
- crash at every transaction boundary => no silent duplicate;
- process identity uncertainty => UNKNOWN, never automatic retry;
- Phase 5 Dry Run remains unchanged and no real-install handler is registered.

## 9. Verification record

This is a design-only document derived from source inspection of the current repository. No runtime code, database schema, Windows storage adapter, worker, process launcher, package manager, download, or installer was changed or executed. No runtime test pass is claimed. Markdown lint/format and CI results must be recorded against the commit that adds this document.
