# P6-609-A — Existing Architecture Reconciliation

## Purpose

This is a source-backed reconciliation of the current `main` implementation against the General Software Installation contract in P6-609. It is documentation only. It does not enable execution or change the Windows host.

## Findings from current main

| Capability | Current implementation | Status for real installation |
|---|---|---|
| Software discovery | `software_discovery.py`, `software_discovery_api.py`; signed Microsoft WinGet catalog and immutable manifest commit reads | Read-only discovery exists; candidates are not install authorization |
| Vendor release validation and staging | `software_staging.py`; official-release match, bounded HTTPS staging and Authenticode identity extraction | Staging exists but is not wired into an approval or execution path |
| Evidence registry | `software_evidence.py`; process-local bounded registry | Default-deny: no publisher signer trust anchors are configured |
| Exact-action approval | `software_approval.py`, `software_approval_api.py`; plan/evidence digest bound to owner/session and TOTP | Confirmation returns `APPROVED_NOT_EXECUTED`; no dispatch or job creation |
| WinGet artifact adapter | `winget_adapter.py`; creates/revalidates a local manifest and fixed argv from immutable binding | Preparation only; no process invocation |
| Job lifecycle | `job_lifecycle.py`; state transitions, leases, cancellation and in-memory reference store | Lifecycle foundation only; not connected to approval or worker |
| Durable job store | `job_store.py`; SQLite operational job persistence | Store exists; no approval producer/worker dispatch integration |
| Job status API | `jobs_api.py` | Read-only; no job creation, start, retry or dispatch |
| Windows process containment | `process_containment.py`; Job Object wrapper | Containment primitive exists; no reviewed suspended-process launcher that creates, assigns-before-resume, supervises and reconciles the WinGet process tree |
| Security audit | `audit.py`, `auth_audit.py` | Current general audit sink is bounded, process-local, optional/best-effort; not a mandatory durable execution ledger |
| Policy | `policy.py`, `tools.py` | Phase 5 policy explicitly allows Dry Run only; R2/R3 denied; no real-install execution mode |
| Step-up state | `step_up.py`, TOTP components | Owner/session/action-bound one-use challenge exists, but challenge/replay state is process-local; restart and cross-process atomicity must be addressed before execution |

## Critical integration gaps

### A. Trust evidence cannot currently authorize an installer

`SoftwareEvidenceRegistry` rejects staged installers unless the signer certificate fingerprint matches a backend-owned publisher trust anchor. No anchors are configured. Do not populate trust from a manifest publisher string, search result, AI output, or frontend value. Add a publisher-specific trust process with independently verified vendor-controlled evidence and negative tests.

### B. Approval is not a dispatch capability

The software approval endpoint intentionally returns `APPROVED_NOT_EXECUTED`. Its process-local binding table and evidence registry are not a durable, atomic approval-to-job ledger. A future producer must atomically reserve the exact approval with a durable job and consume it at the worker's QUEUED-to-STARTING transition, in the same transaction as the execution-boundary audit event and lease creation. A cached approval response must never authorize dispatch.

### C. Worker launch is incomplete

The Windows Job Object wrapper is not a process launcher. Implement a reviewed launcher that:
- accepts only a backend-owned fixed executable identity and typed, immutable argv/environment;
- creates the process suspended;
- assigns it to the Job Object before resuming the primary thread;
- persists process identity and Job Object identity before acknowledging execution start;
- drains stdout/stderr with bounded buffers while continuing to drain;
- handles cancellation, timeout, descendants, backend shutdown, and orphan reconciliation;
- reports UNKNOWN whenever process ownership or side-effect outcome cannot be proven.

No HTTP request handler may start WinGet directly.

### D. Audit is a hard blocker

A mandatory durable execution ledger is required for proposal, approval, reservation, execution-start, preflight denial, completion, failure, partial/unknown outcome, cancellation, and recovery/reconciliation. It must be committed atomically with relevant job/approval transitions. If the ledger cannot commit, dispatch is blocked. Keep optional diagnostic/authentication sinks separate.

### E. Policy remains Dry Run only

The current policy validator deliberately requires every registered tool to use `dry_run` and denies side-effecting risk classes. Do not weaken the Phase 5 policy in place. Introduce a separately reviewed capability-specific policy and fixed handler registration, preserving Dry Run unchanged and default-denying execution until explicit enablement.

### F. Windows-specific WinGet preflight is absent

Before any process creation, verify:
- the actual current-user WinGet executable and its Microsoft signature under a pinned, reviewed signer policy;
- LocalManifestFiles feature state without changing it or elevating;
- approved local manifest files remain locked and byte-for-byte bound to the approval for the entire contained process lifetime;
- supported installer type, user scope, architecture, package/version and silent behavior;
- package agreements, reboot, elevation, machine-wide scope, or other new user-impacting conditions are not silently accepted.

### G. Post-install verification is absent

A zero exit code is not proof of success. Independently verify exact package identity, version, architecture and user scope. Distinguish SUCCEEDED, FAILED, REBOOT_REQUIRED and UNKNOWN; never retry an ambiguous install automatically.

## Recommended implementation order

1. **P6-609-B — Execution security foundation:** close exact-action durable approval reservation/consumption, mandatory durable audit, process launcher/containment lifecycle, restart recovery and failure semantics. Keep policy default-deny.
2. **P6-609-C — WinGet execution integration:** fixed backend worker, executable trust, LocalManifestFiles preflight, locked manifest for full process lifetime, bounded output, cancellation and independent post-install verification. Enable only in a test harness until separate authorization.
3. **P6-609-D — General adapter contract:** retain a common typed interface but separate each package manager's trust model. WinGet first; Chocolatey and Scoop remain disabled until their own script/source/manifest execution models pass independent review.
4. **P6-609-E — First real acceptance:** after independent A4 review, green CI, Windows synthetic process-containment tests, explicit Product Owner enablement, and current vendor/manifest evidence, install DBeaver Community as the first real package. If the manifest and official release still mismatch, block and select a current eligible package only after review; do not bypass trust checks.

## Product behavior preserved

The user experience remains general-purpose: request software → discover exact candidates → review exact package and trust evidence → approve once → backend preflight → automatic installation if every gate passes → independent verification → report and audit. DBeaver is the first acceptance scenario, not a permanent hard-coded allowlist.

The first runtime slice remains deliberately bounded to one exact WinGet package per approval, local Windows 11, user scope, no automatic elevation, no arbitrary commands/scripts, no batch jobs, and no silent acceptance of agreements or reboot. Chocolatey and Scoop are later adapters, not implied enabled capabilities.

## Verification statement

This reconciliation is based on the current source and documentation on `main` at the time this file was prepared. It is not a code review sign-off, A4 security approval, Windows installation test, or authorization to execute an installer.
