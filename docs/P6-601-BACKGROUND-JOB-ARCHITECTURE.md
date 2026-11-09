# P6-601 — Background Job Architecture

## Status and authority

**Status: Product Owner-approved planning direction; documentation only.**

The Product Owner agrees that long-running PC tasks should run asynchronously and be checked later. This decision approves architecture planning only. It does not authorize implementation, launching a BAT file, invoking a package manager, or performing any real machine-changing action.

The first motivating use case is software installation, but the architecture should support other bounded long-running capabilities (for example, approved uninstall or update tasks) without becoming a general-purpose command runner.

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

## Restart recovery and retention — unresolved design gate

The current project policy prohibits persisting chat messages, chat history, or task history, and existing plan/challenge state is process-local. Reliable recovery after backend/process/Windows restart therefore requires an explicit design decision; do not silently introduce durable task-history storage.

Before runtime implementation, A1 must present a minimal job-state persistence proposal for Product Owner approval. It must specify:
- Which operational fields are persisted (and explicitly exclude chat prompts/history and secrets).
- Local storage location, ACL, integrity/tamper protection, atomic state transitions, and corruption handling.
- Retention and deletion policy, including logs and installer output.
- Recovery rules for jobs found in QUEUED, STARTING, RUNNING, VERIFYING, or CANCEL_REQUESTED after restart.
- How to prevent duplicate execution when the prior process may still be running or may have completed before the crash.

Until that decision is approved and implemented, a job whose execution state cannot be proven after restart must be marked UNKNOWN and must not be automatically re-run. Never infer success from a missing process or missing log.

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
- A4 independently reviews the state machine, process-launch boundary, persistence/retention decision, failure semantics, and negative-test evidence.

## Explicit non-goals

This design does not authorize a general command queue, arbitrary BAT/PowerShell/CMD execution, arbitrary script upload, remote job execution, LAN/public access, automatic elevation, automatic retries of ambiguous jobs, or real software installation. Each concrete capability still requires its own bounded task, independent A4 review, tests, CI, and separate Product Owner implementation and enablement approvals.
