# P6-601 — Background Job Architecture

## Status and authority

**Status: Product Owner-approved planning direction; documentation only.** The Product Owner has explicitly approved persistence of operational Job records and configuration, subject to the data boundaries and retention controls below.

The Product Owner agrees that long-running PC tasks should run asynchronously and be checked later. This decision approves architecture planning only. It does not authorize implementation, launching a BAT file, invoking a package manager, or performing any real machine-changing action.

The first motivating use case is software installation, but the architecture should support other bounded long-running capabilities (for example, approved uninstall or update tasks) without becoming a general-purpose command runner. The user also requested Jenkins-inspired job configuration and scheduling; this is a planning requirement, not authorization for arbitrary pipeline scripts or unrestricted CI/CD.

## Design decision

Use a backend-owned **Background Job System**:

1. The user requests a bounded task and receives a preview of the exact action.
2. The backend validates the typed request, source evidence, policy, and exact-action approval.
3. The backend creates one immutable job record with a server-generated Job ID and idempotency key.
4. A backend-owned worker claims the job and invokes only the fixed adapter registered for that tool ID.
5. The initiating HTTP request returns promptly with the Job ID and initial state; it does not wait for installation to finish.
6. The UI/API can poll job status and retrieve an allowlisted progress summary and log excerpt.
7. The worker verifies the outcome independently before marking the job successful.

Gemini/model output may help interpret the user's intent, but it must never create job commands, scripts, handler names, executable paths, or process arguments.

## Jenkins-inspired Job Configuration and Scheduler

Provide a local Job Management UI inspired by the useful parts of Jenkins: saved job definitions, manual “Run now”, schedules, run history, logs, enable/disable controls, and clear execution status. This is not a full Jenkins clone and must not expose arbitrary build agents, plugins, shell steps, or user-authored scripts.

### Job definition model

A saved Job Definition should be declarative, versioned, and validated by the backend. It may contain:
- Stable Job Definition ID, human-readable name, description, enabled/disabled state, and configuration version.
- One fixed backend-owned tool/capability ID selected from the approved catalog.
- Strictly typed parameters with schema validation, bounds, and safe defaults; secret values must use a separately approved secret-storage design and never appear in logs.
- Trigger type: manual, one-time schedule, or recurring schedule using an explicit timezone (default Asia/Bangkok for the UI).
- Optional fixed, backend-owned workflow steps only where each step maps to an approved tool ID and a typed schema. No free-form shell/BAT/PowerShell/CMD, inline script, arbitrary executable, dynamic plugin, or model-authored pipeline.
- Execution timeout, concurrency policy, and a bounded retry policy. Retries for side-effecting actions are disabled by default and may be enabled only when the capability proves idempotency and independently verifies that repeating the action cannot duplicate or compound side effects.
- Notification preference from a fixed allowlist, without adding an unapproved external provider or data flow.

### Scheduling and run controls

- Support manual run, one-time run, and recurring schedules. Persist the timezone and schedule expression; define daylight-saving and missed-run behavior explicitly.
- Provide pause/disable, edit, clone, and run-now controls. Editing a definition creates a new version; every run records the exact immutable definition version and parameter digest used.
- Enforce per-job and global concurrency limits, queue bounds, overlap policy, and scheduler misfire policy. Never silently launch a backlog of missed runs after downtime.
- Scheduled triggers create a run request; they do not bypass policy, source verification, or authorization.
- Read-only scheduled jobs may run under a separately approved bounded policy. A scheduled side-effecting job must not silently inherit a one-time approval: by default it enters an approval-required state for each run. Any standing authorization for recurring side effects would require a separate Product Owner decision, narrow scope, explicit expiry, exact parameter/version binding, and independent A4 review.
- Webhooks, remote triggers, distributed agents, cloud runners, and LAN-accessible scheduler endpoints are out of scope for the current local-first phase.

### Safe workflow model

Jenkins-style stages may be represented as a fixed DAG or ordered list of typed steps, but only if every step has a stable backend-owned tool ID, strict schema, explicit dependency, bounded output, and its own policy/approval requirements. The frontend and model may select only among approved definitions and parameters; they cannot author executable pipeline content. Unknown step types, cycles, dynamic references, and undeclared outputs fail closed.

## BAT / process-launch boundary

A .bat file may be considered only as a minimal, backend-generated launcher for a fixed worker entry point if implementation evidence shows it is necessary. It must be generated from a reviewed, immutable template and must not contain model-authored text or free-form command fragments.

Preferred execution boundary:
- The worker uses a fixed backend-owned adapter and a structured argument vector; process creation must not use shell=True or concatenate user/model strings into a command line.
- If a BAT launcher is retained, it may launch only the fixed worker entry point. It must not become a generic command/script execution feature.
- Installer/package-manager arguments are derived only from validated typed fields and immutable, approved discovery evidence.
- Run with the least privilege required; no automatic elevation. Any privilege change requires a separately approved capability and exact-action confirmation.
- The executable, working directory, environment, arguments, and permitted network/source scope are fixed or strictly allowlisted by the adapter.
- No arbitrary path, URL, script body, shell expression, environment override, or handler name is accepted from the model or frontend.

BAT is a process wrapper, not a security boundary. If safe argument passing, quoting, or injection resistance cannot be demonstrated, do not use BAT; use a direct fixed worker process instead.

## Job lifecycle

Recommended states:

| State | Meaning |
|---|---|
| QUEUED | Validated job awaiting a worker |
| STARTING | Worker has claimed the job and is preparing the fixed adapter |
| RUNNING | The approved operation is in progress |
| VERIFYING | Process ended; independent post-condition checks are running |
| SUCCEEDED | Exit result and required post-condition checks both pass |
| FAILED | Operation failed and the failure is known |
| REBOOT_REQUIRED | Operation reports that a restart is required before final verification |
| CANCEL_REQUESTED | Cancellation was requested; process termination is not yet confirmed |
| CANCELLED | Worker confirms the operation stopped before completion |
| UNKNOWN | State/result cannot be established safely, such as after an unclean shutdown |

A process exit code alone must not establish success. The adapter must map known exit codes (including reboot-related codes where relevant), capture bounded logs, and run a capability-specific post-condition check. Unknown exit codes or contradictory evidence must not be reported as success.

## Job identity, idempotency, and concurrency

- Generate Job IDs server-side; never accept a client-selected ID.
- Bind each job to the authenticated owner/session, tool ID, canonical typed parameters, immutable approval digest, and creation time.
- Enforce one-time approval consumption at the transition into execution, not merely when the job is queued.
- Use an idempotency key derived/stored by the backend to prevent duplicate submissions from retries or double-clicks. A retry must return the existing job result, not launch a second installer.
- Enforce per-tool and global concurrency limits; initially allow at most one active installation job.
- A changed package ID, version, source, installer URL/hash, architecture, scope, privilege, or other approved parameter creates a new proposal and requires fresh approval.
- A queued job whose approval expires or whose evidence no longer matches must be rejected before execution.

## Status API and user experience

The API should return a small, stable job summary: Job ID, tool ID, current state, created/started/finished timestamps, bounded progress message, normalized result code, reboot requirement, and a redacted log reference/excerpt.

- Status polling is read-only and requires the same local authentication boundary as other API routes.
- Polling must never restart, resume, or repeat a job.
- Do not expose raw environment variables, secrets, provisioning data, full command lines, or unbounded installer output.
- The UI should distinguish “accepted/queued”, “running”, “verifying”, “reboot required”, “completed”, “failed”, and “unknown”.
- A timeout or lost browser connection means only that the client stopped waiting; it does not mean the job failed or was cancelled.

## Persistence, restart recovery, and retention — Product Owner-approved scope

The Product Owner explicitly approved persisting **operational Job data** so users can inspect run history and the system can recover safely after backend/Windows restart. This approval does not authorize persistence of chat messages, chat history, Gemini prompts/responses, or unrestricted task transcripts.

Persist only the minimum required operational data:
- Job Definition ID, version, validated typed configuration, enabled state, and schedule/timezone.
- Job Run ID, definition version, tool ID, canonical parameter/evidence digest, owner reference, approval reference/status, lifecycle timestamps, state transitions, normalized exit/result code, reboot requirement, and verification outcome.
- Bounded, redacted operational logs and references to retained artifacts only when required for diagnosis.
- Worker lease/claim metadata and process identity needed for safe recovery, with integrity protection and expiry.

Security and storage requirements:
- Local storage only, protected by restrictive Windows ACLs for the application/user context; use atomic writes/transactions and integrity checks.
- Never persist secrets, TOTP/QR/provisioning data, access tokens, chat prompts/responses, raw model output, arbitrary command lines, or unrestricted machine inventory.
- Encrypt sensitive operational fields at rest where appropriate; document key protection and recovery behavior. Do not invent a key-management scheme in implementation.
- Define configurable retention with conservative defaults, bounded storage/log sizes, automatic expiry, and user-visible deletion of Job Definitions and run records subject to audit/security obligations.
- Keep security audit ledger records logically distinct from user-visible job history; mandatory fail-closed execution auditing remains required for side effects.
- A4 must review the exact schema, ACL, integrity, retention, deletion, corruption, backup, and recovery behavior before runtime enablement.

Recovery rules:
- QUEUED jobs may be re-queued only after revalidating definition version, approval validity, and all preconditions.
- STARTING/RUNNING/VERIFYING jobs discovered after an unclean shutdown must be reconciled against a trustworthy worker lease/process identity and capability-specific post-condition evidence. If execution ownership or outcome is ambiguous, mark UNKNOWN and require user resolution; never automatically re-run.
- CANCEL_REQUESTED jobs require proof of process termination before becoming CANCELLED.
- REBOOT_REQUIRED jobs may transition to SUCCEEDED only after restart and independent post-condition verification.
- Never infer success from a missing process, missing log, or exit code alone.

## Failure, cancellation, and partial completion

- Capture start/end timestamps, normalized exit code, bounded stdout/stderr, and adapter verification results.
- Redact secrets and sensitive machine details before logs are exposed or retained.
- Cancellation is best-effort and must report whether process termination was confirmed. Do not claim rollback unless the adapter has a tested rollback contract.
- If an installer partially changes the machine and then fails, report partial/unknown outcome; do not automatically retry or attempt cleanup.
- Reboot-required is a distinct state. After restart, revalidate the installed product and job identity before transitioning to SUCCEEDED.
- Audit/policy ledger failure must block the start of a side-effecting job. Record execution-start and terminal outcomes using the future mandatory fail-closed execution ledger; the current optional in-memory audit sink is insufficient.

## Required tests before any real capability

Use synthetic fixtures, isolated temporary directories, fake executables, and spy handlers only; do not inspect or mutate the user's live PC.

- No worker dispatch before exact-action approval is consumed.
- Model/frontend cannot control executable, script content, handler, arguments outside schema, environment, working directory, or privilege.
- Invalid, stale, mismatched, replayed, expired, or changed approval never reaches the adapter.
- Duplicate HTTP submissions and worker retries do not create duplicate side effects.
- Worker crash, backend restart, Windows restart, stale lock, corrupt state, and ambiguous process ownership fail closed.
- Exit-code mapping, reboot-required, independent post-condition verification, partial failure, cancellation races, log redaction, and retention are tested.
- Unknown job IDs and cross-session/owner status access are denied.
- Concurrency limits and queue exhaustion are enforced.
- A4 independently reviews the state machine, process-launch boundary, persistence/retention controls, scheduler authorization, failure semantics, and negative-test evidence.

## Explicit non-goals

This design does not authorize a general command queue, arbitrary BAT/PowerShell/CMD execution, arbitrary script upload, remote job execution, LAN/public access, automatic elevation, automatic retries of ambiguous jobs, or real software installation. Each concrete capability still requires its own bounded task, independent A4 review, tests, CI, and separate Product Owner implementation and enablement approvals.


## Normative execution contract addendum — P6-601 A4 remediation

This section is normative for any future implementation. If an implementation
cannot satisfy a rule below, it must remain disabled and fail closed. This
addendum does not authorize a worker, installer, scheduler, or machine-changing
operation.

### Run state transition matrix

Only the following transitions are permitted. All transitions must be persisted
atomically with the associated audit event and version check.

| From | To | Actor | Required preconditions |
|---|---|---|---|
| absent | QUEUED | API | Authenticated owner; schema-valid immutable definition version; current evidence; exact approval reserved (not consumed) in the same transaction; unique idempotency key; queue audit committed |
| QUEUED | STARTING | Worker | Atomic compare-and-set claim; valid unexpired lease; exact approval and evidence revalidated; approval consumed atomically with STARTING and its audit event; no other active installation |
| QUEUED | FAILED | Worker/reconciler | Definitive approval expiry/revocation or evidence mismatch before process creation; terminal rejection audit committed |
| STARTING | RUNNING | Worker | Fixed executable identity verified; process created inside containment boundary; process identity persisted before side-effect start is acknowledged |
| STARTING | FAILED | Worker/reconciler | Definitive proof no child/installer process started; terminal audit committed |
| STARTING | UNKNOWN | Reconciler | Process creation outcome or ownership cannot be established |
| RUNNING | VERIFYING | Worker | Contained process tree has exited; descendants reconciled; bounded output finalized |
| RUNNING | CANCEL_REQUESTED | API | Owner authorized; cancellation request persisted; no claim that process has stopped |
| CANCEL_REQUESTED | VERIFYING | Worker/reconciler | Completion is proven and the contained process tree has exited; reconcile descendants and finalize bounded output before post-condition checks |
| CANCEL_REQUESTED | CANCELLED | Worker/reconciler | Job Object and descendant inspection prove all associated processes terminated before side effects completed |
| CANCEL_REQUESTED | UNKNOWN | Reconciler | Termination or partial side effects cannot be proven |
| VERIFYING | SUCCEEDED | Worker | Independent package identity, version, scope and required postconditions all pass |
| VERIFYING | REBOOT_REQUIRED | Worker | Trusted adapter result explicitly requires reboot; pre-reboot verification is insufficient |
| VERIFYING | FAILED | Worker | Failure is definitive and postcondition checks prove requested state absent |
| VERIFYING | UNKNOWN | Worker/reconciler | Contradictory, incomplete or ambiguous evidence |
| REBOOT_REQUIRED | SUCCEEDED | Reconciler | After restart, process absence and independent postcondition verification both pass |
| REBOOT_REQUIRED | UNKNOWN | Reconciler | Restart recovery cannot prove the final state |
| any nonterminal | UNKNOWN | Reconciler | Lease/process ownership lost, durable state corrupt, or outcome ambiguous |

All other transitions are forbidden. In particular: no transition from UNKNOWN
back to QUEUED/STARTING/RUNNING; no automatic retry after timeout, crash,
ambiguous process ownership, or partial side effect; no transition to SUCCEEDED
based only on exit code, missing process, or missing log. Resolution of UNKNOWN
requires a new user-reviewed proposal and fresh approval, never replay of the
old run.

### Durable record and transaction contract

The minimum durable schema is versioned and local-only:

- `job_definitions`: definition_id, definition_version, enabled, fixed_tool_id,
  canonical_typed_config, schedule_timezone, schedule_spec, created_at,
  updated_at, integrity_version.
- `job_runs`: run_id, definition_id/version, owner_reference, tool_id,
  canonical_parameter_digest, evidence_digest, approval_id, idempotency_key,
  state, state_version, created_at, started_at, finished_at, result_code,
  reboot_required, verification_result, bounded_log_reference.
- `job_approvals`: approval_id, owner/session binding, exact action digest,
  evidence digest, issued_at, expires_at, consumed_at, consumed_by_run_id.
- `worker_leases`: run_id, worker_instance_id, lease_generation, acquired_at,
  expires_at, heartbeat_at, process_id, process_creation_time, job_object_id.
- `job_events`: run_id, monotonically increasing sequence, prior_state,
  next_state, actor, occurred_at, reason_code, state_version.

Use a transactional local database with integrity constraints and a single
writer/transaction boundary. The queue transaction must:
(1) compare the exact owner/session/action/evidence digests and initial expiry;
(2) reserve (but do not consume) the one-use approval for this immutable run;
(3) insert exactly one QUEUED run with its idempotency key; and
(4) append the queue audit event. If any step fails, roll back all four. A
duplicate idempotency key returns the existing run and never creates a second
run. A reservation that expires before execution is not consumed and must be
released or rejected through an audited terminal transition.

Worker claim is a separate atomic transaction: compare QUEUED + expected
state_version, ensure no unexpired lease and concurrency slot is available,
then revalidate exact owner/session/action/evidence digests and expiry. If
revalidation fails, atomically transition QUEUED to terminal FAILED and append
the rejection audit event; do not create a lease or process. If it succeeds,
atomically consume the reserved approval, write STARTING, create the unique
lease generation, and append the execution-boundary audit event. A stale lease
is not proof that a process stopped. Recovery must inspect the persisted process
creation time and containment object; ambiguity moves the run to UNKNOWN.

Before process creation, persist an execution-intent record and reserve the
one-use approval. Immediately after process creation, persist PID plus process
creation timestamp and Windows Job Object identity before reporting RUNNING.
A crash between process creation and identity persistence is UNKNOWN and must
not trigger another launch.

### Windows process containment contract

A Windows worker must create the child suspended, assign it to a newly created
Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then resume
only after assignment and process identity persistence succeed. The Job Object
must disallow breakaway. The worker retains the Job Object handle for the full
run. Cancellation terminates the Job Object and waits for all associated
processes to exit; it must not kill by image name or PID alone. If assignment,
query, termination, or descendant reconciliation fails, mark UNKNOWN. If the
installer escapes containment or a descendant remains, execution is not
considered stopped. A4 must inspect the exact native API flags, handle lifetime,
race handling, and tests before enablement.

### Scheduler semantics

Schedules use an explicit IANA timezone, default `Asia/Bangkok`. Persist the
timezone and the evaluated UTC occurrence. For a nonexistent local time during
a DST spring-forward gap, skip that occurrence and record MISFIRE_SKIPPED. For
an ambiguous fall-back local time, execute only the first occurrence (earlier
UTC instant) and persist the deduplication key. On downtime, do not catch up
missed recurring runs automatically; record skipped occurrences. One-time
schedules that are missed while the backend is stopped become EXPIRED. Overlap
policy is fixed to FORBID for installation jobs; a scheduled trigger creates a
new approval-required proposal and never inherits prior approval. No automatic
catch-up, coalescing into an unreviewed action, or standing side-effect
authorization is permitted.

### Threat-to-control-to-test release matrix

| Threat | Required control | Required negative/acceptance test |
|---|---|---|
| Double submit or API retry | Unique idempotency constraint + atomic approval consume/run insert | Concurrent duplicate requests create one run and one consumed approval |
| Crash at approval/job boundary | Single DB transaction + mandatory audit | Inject crash before/after each write; either full rollback or one complete QUEUED run |
| Two workers claim one run | Compare-and-set state version + lease generation | Parallel claims yield exactly one STARTING owner |
| Stale lease while installer survives | Lease is not execution proof; inspect Job Object/process creation identity | Orphan process forces UNKNOWN and never requeues |
| Child spawns descendants | Non-breakaway Windows Job Object containment | Descendant remains in Job Object; close/cancel terminates complete tree |
| PID reuse | PID + process creation timestamp + Job Object identity | Reused PID cannot be mistaken for original process |
| DST/misfire duplicate | Persist timezone + UTC occurrence dedupe key | Gap skipped; fold runs once; downtime never auto-catches up |
| Approval/evidence mutation | Canonical digest equality at consume and claim | Any changed package/version/source/hash/scope requires new approval |
| Audit storage failure | Mandatory transactional fail-closed ledger | Ledger failure prevents process creation |
| Exit code lies or incomplete install | Independent package identity/version/scope verification | Exit 0 with absent/wrong package never yields SUCCEEDED |

No runtime work may start until the schema/migration, transactional semantics,
native process containment, scheduler behavior, recovery model, and this matrix
have a concrete implementation plan reviewed by A4.
