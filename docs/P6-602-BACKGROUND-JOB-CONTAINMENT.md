# P6-602 — Background Job and Process Containment Foundation

## Status

**Foundation only. Not connected to API dispatch, approval consumption, WinGet, or installer execution.**

This change introduces two isolated primitives:

- `job_lifecycle.py`: a thread-safe reference state machine with idempotent job creation, owner-bound reads, worker leases, compare-and-swap version checks, cancellation requests, and fail-closed lease expiry.
- `process_containment.py`: a Windows Job Object wrapper configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and `JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION`. It supports assigning a process handle before the primary thread is resumed, terminating the contained process tree, and closing the Job Object.

The worker store is intentionally in-memory and test-only. It is not durable, does not survive process restart, and must not be used by the application runtime.

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

1. Durable, atomic local persistence with reviewed Windows ACL/owner/reparse-point protections, corruption handling, retention, and recovery.
2. A production worker loop and scheduler with bounded queue/concurrency, lease renewal, worker shutdown semantics, and crash recovery.
3. A reviewed suspended-process launcher that creates the process with a fixed executable/argv/environment and assigns it to the Job Object before resume. The current wrapper does not create processes.
4. Bounded asynchronous stdout/stderr draining, output redaction, output-size caps, and timeout supervision.
5. Cancellation/timeout race handling, process-tree termination proof, orphan reconciliation, and UNKNOWN outcomes after ambiguous shutdown.
6. One-use approval consumption and atomic binding of approval, immutable action digest, and durable Job record.
7. Capability-specific independent post-install verification and reboot-required handling.
8. Windows acceptance tests that launch a harmless synthetic parent/child process suspended, assign it to the Job Object, resume it, and prove closing/terminating the job stops the complete process tree.
9. Independent A4 review of the exact implementation and negative-test evidence.

No real WinGet process or installer is started by this foundation. Runtime remains disabled until all prerequisites, CI, Windows acceptance, and independent A4 review pass.
