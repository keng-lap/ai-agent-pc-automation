# P6-609 — General Software Installation

## Status and authority

**Product Owner direction: implementation planning and capability design authorized on 2026-11-17.** The intended product capability is general software installation through supported package-manager adapters, not a DBeaver-only installer.

This document does not itself enable real installation. Runtime execution remains blocked until the capability-specific security prerequisites, independent A4 review, CI evidence, and explicit enablement approval are complete. No installer or package manager may be invoked as part of this planning task.

## Product decision

The user-facing capability is **General Software Installation**:

- A user may request any supported software package, not only a hard-coded demonstration application.
- The system discovers candidate packages and presents the exact package identity and trust evidence.
- The user reviews and approves one immutable installation action.
- After approval, the backend automatically performs pre-install checks and, if every check passes, installs the approved package and verifies the result. The user must not have to press a second generic “start install” button.
- If a check fails, the system stops and reports the reason. A materially changed package, version, publisher, source, installer, privilege scope, or action requires a new review and approval.

DBeaver Community is the first end-to-end acceptance scenario, not a permanent allowlist restriction. The architecture must support other eligible packages through the same policy and adapter contracts.

## Package-manager strategy

Use the previously approved Multi-Package Manager direction:

1. **WinGet** — primary adapter for Windows desktop software.
2. **Chocolatey** — secondary adapter, enabled only after its package-script and source-trust model has its own reviewed contract.
3. **Scoop** — additional adapter, enabled only after its bucket/manifest and installer provenance model has its own reviewed contract.

A common package-manager interface may normalize discovery, package identity, preflight, installation, verification, and result reporting. It must not normalize away source-specific trust requirements. Each adapter is a fixed backend-owned implementation selected by a server-side enum; no client or model may supply a handler name or command line.

## Required user workflow

1. **Request:** User names the product and, when needed, edition, version, architecture, or install scope.
2. **Discovery:** Search supported package sources and resolve exact candidates. A search result is not trusted installation evidence.
3. **Review:** Show product/edition, package ID, publisher, version, source, installer origin, integrity and signature evidence, architecture, scope, privilege requirements, dependencies, and material limitations.
4. **Approve:** The user explicitly approves the immutable action. High-risk step-up uses the existing Authenticator App, with proof bound to the exact evidence and action digest.
5. **Pre-install checks:** After approval, the backend revalidates evidence freshness and digest, package-manager identity/trust, host prerequisites, install state, scope, privileges, and job/worker availability. These checks do not broaden the approved action.
6. **Install:** If all checks pass, the backend-owned worker invokes only the fixed adapter with typed, validated arguments derived from the approved evidence. No second generic start confirmation is required.
7. **Verify:** Independently inspect the installed package identity, version, architecture, and scope. Exit code zero alone is not success.
8. **Report:** Return a truthful terminal result and bounded audit/job events. If the outcome is uncertain, report UNKNOWN/VERIFYING rather than success or a clean failure.

## Initial runtime boundary

The first real-execution slice should be WinGet and one package at a time, while the product architecture remains general:

- Windows 11 local machine only; loopback-only application.
- User-scope installation only. No automatic elevation, administrator consent, machine-wide installation, or policy changes.
- One exact package/version per approved job; no batch install, automatic dependency expansion, update, uninstall, or arbitrary maintenance task in this slice.
- Only package types and installer behaviors with a reviewed, fixed, silent/non-interactive contract are eligible.
- No arbitrary shell, PowerShell, CMD, BAT, scripts, installer switches, URLs, executable paths, download destinations, or model-generated process arguments.
- No package-provided scripts or custom commands unless a future adapter-specific design explicitly reviews and constrains them.
- Do not silently accept source/package agreements, reboot, close applications, or change Windows settings. Stop and ask for a new explicit user decision when such an action is required.
- If the requested package is already installed at the requested version/scope, report that state and do not reinstall.
- No automatic retry after an uncertain or partial install. Reconcile the process and installed state first.

The first real installation is an acceptance test of the general workflow; it is not permission to remove the per-package provenance and policy checks.

## Security and release gates

The following are hard blockers before any real package-manager invocation:

1. Complete the independent A4 review of the merged Google OIDC, Windows DPAPI, Authenticator App TOTP, exact-action binding, replay/expiry, and bypass resistance. The Phase 5 residual is not an A4 pass.
2. Resolve the current step-up and approval-cache/idempotency review findings. Prove one approval cannot authorize another package, changed evidence, another session, or a replayed job.
3. Design and implement a mandatory, durable, privacy-bounded audit ledger for side effects. The current optional in-memory audit sink is insufficient.
4. Verify the WinGet executable identity and Microsoft signature using a reviewed trust policy. PATH presence or an alias alone is insufficient.
5. Detect the WinGet LocalManifestFiles prerequisite without changing it. Never enable it automatically or elevate.
6. Keep the approved local manifest locked and revalidated for the entire contained WinGet process lifetime.
7. Implement and independently test Windows process-tree containment, bounded output draining, cancellation, timeout/orphan reconciliation, and truthful UNKNOWN outcomes.
8. Configure publisher trust anchors only from independently verified vendor-controlled evidence. Unknown or mismatched signers remain blocked.
9. Verify the installed package identity/version/scope independently after execution.
10. Integrate through the backend-owned fixed handler and approved background-job lifecycle. No HTTP request handler may directly launch an installer.
11. Add negative tests proving policy denial, stale/replayed approval, evidence substitution, signer mismatch, manifest tampering, missing prerequisites, worker failure, and audit failure cannot reach or silently authorize execution.
12. Complete CI, independent A4 review of the implementation, and local Windows acceptance before a separate explicit Product Owner enablement decision.

## DBeaver first acceptance case

DBeaver Community is the first candidate to exercise the workflow. The current discovery documentation reports that the WinGet manifest version and official DBeaver release did not match at the time of its check. Therefore:

- Do not assume the existing DBeaver.DBeaver.Community candidate is currently trusted or installable.
- Re-run live discovery and vendor release verification at test time.
- Require exact package ID, version, installer URL, SHA-256, Authenticode signer fingerprint, and user scope to agree.
- If the manifest remains stale or any trust evidence is unavailable, block the installation and report the mismatch. Do not bypass the check by using a guessed Package ID or direct URL.

## Acceptance criteria

- A user can request multiple different supported products without adding each product name to application code.
- Search results are candidates only; the user selects an exact package identity.
- The approval digest binds every material package, source, installer, version, architecture, scope, and privilege field.
- After one successful approval, backend preflight and installation proceed automatically only when all gates pass.
- A failed preflight causes zero installer invocations.
- A changed or expired approval/evidence causes zero installer invocations.
- Arbitrary commands and client/model-supplied executable data are rejected.
- The first real WinGet install is verified independently and reported truthfully.
- Existing Dry Run behavior remains unchanged and continues to make no machine changes.
- Chocolatey and Scoop remain disabled until their own adapter-specific security gates pass.

## Out of scope

- Remote/LAN or mobile PC control.
- Public internet control plane or cloud worker.
- Arbitrary command execution, scripts, shell access, or user-defined pipelines.
- Batch installation, uninstall, update, scheduled installation, and automatic dependency installation.
- Automatic privilege escalation or machine-wide installation.
- Enabling real execution merely because Phase 6 planning or this document is approved.

## Work breakdown

- **P6-609-A — Reconcile current architecture and open security blockers.** Map existing discovery, evidence, approval, staging, manifest adapter, background job, containment, and audit code to this contract.
- **P6-609-B — Close shared authorization, audit, and worker prerequisites.** No installer dispatch until independent A4 review passes.
- **P6-609-C — WinGet execution integration.** Fixed adapter dispatch through a contained background worker; typed preflight and post-install verification.
- **P6-609-D — General package-manager contract.** Add Chocolatey and Scoop only through separate source-specific trust and execution reviews.
- **P6-609-E — First real acceptance.** DBeaver Community, subject to current vendor/manifest/signature evidence, on the Product Owner's Windows 11 Home machine after explicit enablement approval.
