# P6-609-B2 Durable Approval and Job Reservation

## Status

**In progress / not production-ready.** The approved implementation sequence and baseline gaps are recorded here. A first isolated SQLite store and tests have been added, but API integration, Windows secure storage, CI validation, and independent review remain incomplete. This is not evidence that the application can execute installations.

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

- Same approval + same idempotency key + same exact binding returns one stable reservation receipt, including concurrent calls through two independent store instances.
- Same key with a different owner/session/plan/action digest is rejected.
- Approval expiry immediately before reservation creates no reservation and records the expiry transition.
- Revocation racing reservation has exactly one serialized winner; no revoked approval can produce a queued job.
- Duplicate confirmation/replay cannot create a second reservation.
- Database error or audit-write error rolls back both approval and reservation changes.
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

## Implementation update — 2026-11-19

### B2.1 / B2.2 first isolated store slice

Branch: `feat/P6-609-B2-durable-approval-reservation`

Commits:
- `5e08ba8d56395696ef6c581b29a971ec949dfe24`: add `approval_reservation_store.py`.
- `743406f057b7522fc4c529a57592f6abddcea704`: add focused store tests.
- `572bac32afa848738086b52f75025f1ad32260d8`: classify reservation audit-write failures as store-unavailable, so they fail closed.
- `092283bfdcee2b0b84ce2c9de994525c424e3411`: assert the audit failure is surfaced as unavailable.
- `2d16366c3a119ec31c89c8f713b44d965edf7677`: remove an unused state constant.
- `e41832b457758bb910f7ee90794000465da6b749`: add barrier-coordinated concurrent idempotency and reserve/revoke tests.

Implemented in this slice:
- Separate SQLite schema for immutable approval bindings, inert reservation receipts, and allowlisted approval audit events.
- `BEGIN IMMEDIATE` serialization and database uniqueness for approval consumption and idempotency.
- Exact owner/session/plan/plan-digest/action-digest matching.
- Backend-clock expiry transition persisted with its denial audit event.
- Revocation and reservation serialized against the same database.
- Exact retry returns the original reservation receipt; a mismatched retry is rejected.
- Owner-scoped reservation lookup.
- Audit insertion shares the state-transition transaction; a failed audit insert rolls back reservation and approval-state changes.
- Tests added for restart durability, idempotency across independent store instances, binding mismatch, owner isolation, expiry, barrier-coordinated concurrent reserve/revoke, and audit rollback.

Not yet implemented / not yet proven:
- The new store is not wired into `software_approval_api.py`; existing process-local approval state remains in the live API path.
- The reservation is intentionally an inert `RESERVED` receipt, not a queued worker job and not a dispatch capability.
- The new store uses the existing secure-storage adapter interface. The repository's default adapter still rejects Windows; therefore this code is not production-usable on the target Windows machine until the native Windows DACL/owner-SID/reparse-point/handle-race adapter is implemented and reviewed.
- No test suite or Ruff run has been executed in this work slice; CI evidence is pending.
- No independent security review has been completed.

The first test slice is intentionally isolated. Do not treat B2 as complete, do not merge this branch, and do not proceed to B3/B4/P6-609-C or real installation until the remaining gates are satisfied.

## Work-log correction

The earlier entry saying no runtime code had changed describes the initial note-only commit at that time. It is historical and is superseded by the implementation updates above.

- 2026-11-19: Clarified the implemented B2 lifecycle: approval state is `ACTIVE` before consumption and becomes `RESERVED`, `EXPIRED`, or `REVOKED`; the associated reservation remains inert and is not handed to a worker in B2.


### Additional B2 hardening — append-only records

- Added SQLite triggers to prevent mutation/deletion of approval identity and evidence bindings after creation.
- Added append-only enforcement for approval audit events.
- Added immutable reservation receipt enforcement; B2 reservations cannot be changed into `QUEUED` by direct database updates.
- Added a regression test that attempts each prohibited SQL mutation directly.
- This is defense in depth, not a substitute for Windows filesystem ACL protection. Windows storage remains fail-closed until its dedicated adapter is implemented and reviewed.


### Windows SQLite storage design gate — 2026-11-19

The existing `WindowsSecretFile` implementation must not be reused as if it were a SQLite adapter:

- It is designed for one bounded secret file and performs I/O through a verified Windows handle.
- The Python SQLite connection in this repository opens a database by pathname and may create companion files such as `-wal`, `-shm`, or rollback journals.
- Securing only the main database file after SQLite opens it would leave a creation/ACL window and would not prove that companion files inherit a restrictive ACL.
- Checking a path and then passing that path to SQLite is not equivalent to keeping the checked file identity pinned through the open.

Therefore Windows remains fail-closed. The next adapter design must prove, before enabling it:
1. Current-user SID ownership and a protected owner-only DACL on the database directory, with correctly scoped inheritance for SQLite companion files.
2. Reparse-point rejection and safe handling of pre-existing database and companion files.
3. No unsafe path replacement between validation and SQLite open; if the standard SQLite pathname API cannot meet the required handle-race boundary, use a reviewed VFS/handle strategy or explicitly narrow and approve the threat model rather than claiming handle safety.
4. Windows CI coverage for create/open/reopen, WAL and rollback-journal behavior, ACL inheritance, owner mismatch, reparse points, and concurrent access.

Do not weaken the existing `WindowsSecretFile` checks or enable Windows by simply returning a new adapter from the platform factory.

### Validation snapshot — 2026-11-19

At head `af3bab6435e61c6a62c9b80293f2555bec4eee36`:
- Backend tests: passed.
- AI reviewer unit tests: passed.
- Ruff: passed.
- CodeQL Python, JavaScript/TypeScript, and Actions analyses: passed.
- Frontend unit tests: passed; Playwright desktop/mobile viewport E2E and frontend build were still running at the time of this note.
- CodeRabbit: no submitted review exists because PR #168 remains Draft. Its comment explicitly says Draft PRs are not automatically reviewed by default.


### Windows SQLite adapter implementation slice — 2026-11-19

Implemented a dedicated `WindowsSQLiteStorage` adapter and wired both SQLite approval-reservation and operational job stores to request a path-bound platform adapter.

Security behavior implemented:
- Pins verified directory/ancestor handles for the adapter lifetime using the existing Windows handle-opening primitive; the handles deny delete sharing to block directory replacement by another Windows identity while SQLite uses pathname I/O.
- Applies and verifies a protected current-user-only directory DACL with object/container inheritance so newly created SQLite database, WAL, SHM, and rollback-journal files inherit the owner-only access rule at creation.
- Validates pre-existing database and sidecar files by handle, rejects reparse-point files and non-regular files, verifies owner SID, and repairs only the DACL of files already owned by the current user.
- Revalidates database-directory ACL and existing SQLite files after initialization.
- Adds Windows-only integration tests for WAL/SHM ACLs, directory rename denial while pinned, and pre-existing database reparse-point rejection.
- Extends the Windows CI workflow to run the SQLite storage, platform-selection, and approval reservation tests.

Important limits / acceptance gates:
- Windows integration tests have not yet run on this new commit; wait for the Windows runner result before claiming the adapter is validated.
- The design protects against other Windows identities replacing the protected directory; it does not claim protection against another process running as the same Windows user.
- Existing path-based SQLite behavior still needs independent security review and Windows acceptance. The adapter remains fail-closed if any ACL/owner/reparse verification fails.
- API integration is still outstanding. No Worker, process creation, WinGet, or install execution is added.


### Windows enablement gate retained — 2026-11-19

The Windows SQLite adapter is present for isolated Windows CI/security evaluation, but the platform factory deliberately continues to reject Windows. It is not enabled for the live approval or job stores yet.

Reason: the current handle-pinning/pathname-SQLite design protects against other Windows identities replacing the secured directory, but it does not protect against another process running as the same Windows user. This threat-model boundary has not been explicitly approved by the project owner. Windows enablement therefore requires:
- successful Windows runner results for the adapter's ACL, sidecar, reparse-point, and directory-rename tests;
- independent security review of the path-based SQLite integration and ACL inheritance assumptions;
- explicit project-owner acceptance of the same-user-process threat-model boundary, or a stronger design that removes that limitation.

Until all three are satisfied, `create_platform_secure_storage(platform="win32")` remains fail-closed. The new adapter must not be treated as production-enabled merely because it is importable or its tests pass.
