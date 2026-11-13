# P6-602 — Background Job and Process Containment Foundation

## Status

**Durable status foundation only. Not connected to approval consumption, worker dispatch, WinGet, or installer execution.**

This change introduces two isolated primitives:

- `job_lifecycle.py`: an in-memory reference state machine with owner-bound reads, worker lease semantics, compare-and-swap version checks, cancellation requests, and fail-closed lease expiry.
- `job_store.py`: a local SQLite operational store with transactional idempotent creation, owner-scoped reads, bounded response/event summaries, optimistic version checks, and validated lifecycle transitions.
- `jobs_api.py`: read-only authenticated `GET /api/jobs` and `GET /api/jobs/{job_id}` endpoints. They never create, start, retry, cancel, or dispatch jobs.
- `process_containment.py`: a Windows Job Object wrapper configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and `JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION`. It supports assigning a process handle before the primary thread is resumed, terminating the contained process tree, and closing the Job Object.

The original in-memory reference store remains test-only. The SQLite store persists operational records across process restarts. On POSIX it requires a private 0700 state directory and 0600 database file and rejects symlink paths. **On Windows it intentionally refuses to initialize until native DACL, owner SID, reparse-point and handle/path-race protections are implemented and independently reviewed.** The Frontend will therefore receive HTTP 503 for job status on Windows until this gate is closed.

## Status API and persistence boundary

- The API requires an authenticated Master User session; auth-disabled mode returns 503. Owner scoping is enforced in SQL, and foreign-owner Job IDs are indistinguishable from missing IDs (404).
- SQLite uses WAL, foreign keys, full synchronous commits, `BEGIN IMMEDIATE` write transactions, and a unique `(owner_id, idempotency_key)` constraint.
- Persisted fields are limited to owner reference, fixed tool ID, action digest, idempotency key, state/version/timestamps, normalized progress/result metadata, reboot flag, and bounded event summaries. No prompts, Gemini content, secrets, raw process output, command lines, executable paths, or scripts are stored.
- The status API returns at most 25 jobs and 20 recent events per job. Polling is read-only and cannot alter a job or dispatch work.
- No producer currently creates jobs from the approval workflow. The endpoint returns an empty list until a separately reviewed producer is connected.
- Windows storage is fail-closed pending native ACL/reparse-point implementation; do not bypass the guard.

## Security boundaries

- No process is created or launched by these modules.
- No command line, executable path, environment, working directory, script, or handler name is accepted.
- No dynamic dispatch or arbitrary command execution exists.
- A process must be created suspended by a future reviewed launcher; it must be assigned to the Job Object before its primary thread is resumed.
- If assignment fails, the caller must not resume the process and must terminate/reconcile it.
- The Job Object does not permit breakaway flags. Child processes created by a contained process remain subject to the job unless Windows rejects the child creation.
- Closing the Job Object handle is configured to terminate contained processes. Failure to close the handle must be treated as a containment failure, not as successful cancellation.

## Lifecycle contract

Allowed lifecycle transitions are defined centrally in `job_lifecycle.py`. A worker claim moves a job from `QUEUED` to `STARTING` and issues an unguessable lease token. Every worker transition requires the current worker ID, lease token, and record version. Stale versions, expired leases, invalid transitions, and cross-owner reads fail closed.

Cancellation is split into request and confirmation:

- A queued job can become `CANCELLED` without dispatch.
- A starting/running job becomes `CANCEL_REQUESTED`.
- It becomes `CANCELLED` only after the worker confirms process-tree termination.
- If the worker lease expires while a job is active, the job becomes `UNKNOWN`; it is never automatically re-queued or retried.

The state machine intentionally does not infer success from process exit. A future adapter must move through `VERIFYING` and independently verify its post-condition before `SUCCEEDED`.

## Not yet implemented — required before runtime

1. Native Windows ACL/owner/reparse-point and handle/path-race protections for the SQLite state directory/database; corruption recovery and retention policy still require implementation and A4 review.
2. A production worker loop and scheduler with bounded queue/concurrency, lease renewal, worker shutdown semantics, and crash recovery.
3. A reviewed suspended-process launcher that creates the process with a fixed executable/argv/environment and assigns it to the Job Object before resume. The current wrapper does not create processes.
4. Bounded asynchronous stdout/stderr draining, output redaction, output-size caps, and timeout supervision.
5. Cancellation/timeout race handling, process-tree termination proof, orphan reconciliation, and UNKNOWN outcomes after ambiguous shutdown.
6. A reviewed producer that atomically consumes a one-use approval and binds its immutable action digest to the durable Job record.
7. Capability-specific independent post-install verification and reboot-required handling.
8. Windows acceptance tests that launch a harmless synthetic parent/child process suspended, assign it to the Job Object, resume it, and prove closing/terminating the job stops the complete process tree.
9. Independent A4 review of the exact implementation and negative-test evidence.

No real WinGet process or installer is started by this foundation. Runtime remains disabled until all prerequisites, CI, Windows acceptance, and independent A4 review pass.
