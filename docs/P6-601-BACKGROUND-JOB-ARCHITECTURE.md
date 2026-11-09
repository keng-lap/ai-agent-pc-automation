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
