# P6-609-B2 Durable Approval and Job Reservation

## Status

**Planned / implementation not yet complete.** This note records the approved implementation sequence and the verified baseline gaps. It is not evidence that durable approval, job reservation, or real execution has been implemented.

## Product-owner direction

Proceed with the P6-609 execution-readiness plan in small, independently reviewable stages. Preserve the existing local-first Windows scope and explicit human approval. The first real-install acceptance target remains DBeaver, but no real installer execution is authorized by this work item.

## Baseline verified on 2026-11-19

Repository: `keng-lap/ai-agent-pc-automation`

Main baseline inspected: `c8ba0324174fc90779f55d5ad7fe0d29dfb01082`

Related work:
- PR #167 (`feat/P6-609-general-software-installation`) is still Draft and must not be merged as part of this task.
- PR #167 head at inspection: `5632aa455486cc922725e2a611d4418474aeb787`; its branch was 24 commits ahead and 1 commit behind main.
- PR #167 CI passed at that head, including backend tests and Ruff, frontend tests, Playwright, and build. This does not establish real-execution readiness.
- Main `software_approval_api.py` keeps approval state in process-local `_bindings` and `_consumed_bindings`; successful confirmation returns `APPROVED_NOT_EXECUTED`.
- Main `step_up.py` documents process-local challenge/replay state.
- Main `job_store.py` provides SQLite job history, but does not itself implement approval reservation or dispatch.
- Main `process_containment.py` provides Windows Job Object primitives but explicitly does not create processes or connect to a dispatch path.
- Main `auth_audit.py` and `audit.py` are bounded in-memory diagnostic sinks, not durable execution audit ledgers.

## Scope of B2

Implement only the durable authorization/reservation boundary needed before any worker or OS process can be introduced:

1. Persist an immutable approval record bound to:
   - authenticated owner and session identity;
   - plan ID and plan digest;
   - exact package/evidence approval digest;
   - evidence expiry and backend-created timestamps;
   - one-use approval lifecycle state and version.
2. Persist the associated job reservation atomically with approval consumption, using a single SQLite transaction and a unique idempotency binding.
3. Enforce backend-time expiry and explicit terminal transitions:
   - `RESERVED -> EXPIRED`;
   - `RESERVED -> REVOKED`;
   - `RESERVED -> QUEUED` only as the durable reservation-to-job handoff defined by the reviewed contract.
4. Reject reuse of an approval for a different owner, session, plan, action digest, or job.
5. Ensure retries return the same existing job receipt only when owner, approval, digest, and idempotency binding all match exactly; otherwise return a conflict.
6. Persist mandatory allowlisted audit events in the same transaction as each security-relevant state transition. Audit failure must roll back the transition.
7. Provide owner-scoped retrieval and recovery behavior without exposing secrets, TOTP values, raw prompts, or unnecessary personal data.

## Explicit non-goals

- No worker loop, background dispatch, process creation, WinGet/Chocolatey/Scoop invocation, download, or installation.
- No change that enables real execution or weakens Dry Run.
- No public internet, remote/mobile control, multi-machine execution, or multi-worker deployment.
- No recovery-code, WebAuthn, or alternate-factor feature; these remain out of scope.
- No merge of PR #167 or any other PR.
- No automatic trust of arbitrary publishers or package sources.

## Required implementation and test sequence

### B2.1 Contract and schema
- Define strict immutable approval/reservation records and allowed state transitions.
- Define SQLite schema, uniqueness constraints, foreign keys, transaction boundaries, and schema migration behavior.
- Confirm the secure Windows database path/ACL integration before treating the store as production-capable.

### B2.2 Atomic reservation
- Add a store operation that atomically validates a still-reserved, unexpired approval and creates or returns exactly one matching job reservation.
- Use `BEGIN IMMEDIATE` or equivalent serialization and enforce database uniqueness, not only Python locks.
- Make approval expiry/revocation race-safe against reservation.
- Do not add a dispatch capability to this store.

### B2.3 Durable audit and recovery
- Append allowlisted audit events in the same transaction as the state change.
- Add restart/reopen tests proving persisted state and audit records survive process/store recreation.
- Fail closed if the database or secure-storage adapter is unavailable or inconsistent.

### B2.4 API integration
- Replace process-local approval consumption only after the durable store contract is tested.
- Keep the confirmation response explicitly non-executing until a later, separately reviewed worker/launcher stage exists.
- Ensure no endpoint can start a process or invoke a package manager.

## Mandatory acceptance tests

- Same approval + same idempotency key + same exact binding returns one stable job receipt, including concurrent calls through two independent store instances.
- Same key with a different owner/session/plan/action digest is rejected.
- Approval expiry immediately before reservation creates no job and records the expiry transition.
- Revocation racing reservation has exactly one serialized winner; no revoked approval can produce a queued job.
- Duplicate confirmation/replay cannot create a second reservation.
- Database error or audit-write error rolls back both approval and job changes.
- Reopen/restart preserves approval state, job reservation, and audit history.
- Owner A cannot read or mutate owner B's approval/job.
- No test path creates an OS process or invokes a package manager.

## Validation and release gates

- Run targeted backend tests, the full backend suite, and Ruff; do not claim success until CI reports each required check as successful.
- Add concurrency tests using two independent SQLite store instances against the same database file.
- Run the Windows-specific storage/ACL tests on Windows CI. Linux-only success is insufficient for Windows acceptance.
- Obtain independent review of transaction/race semantics and the updated threat model.
- Keep the branch/PR Draft until B2 implementation, tests, and review evidence are complete.
- B2 completion does not authorize B3, B4, P6-609-C, or real installation. Each stage remains separately gated.

## Work log

- 2026-11-19: Created this implementation note and a dedicated branch from current main after inspecting PR #167 and the main approval/job/step-up/audit/containment paths.
- 2026-11-19: No runtime code changed, no tests were run in this work slice, no PR was merged, and no machine-changing action was performed.
