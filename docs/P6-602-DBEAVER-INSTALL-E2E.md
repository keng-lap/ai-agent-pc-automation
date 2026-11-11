# P6-602 — DBeaver Community Real Installation E2E Capability

- **Status:** Product Owner authorized capability preparation and gated implementation on 2026-11-11.
- **Execution status:** DISABLED. This document does not authorize downloading, installing, launching an installer, changing Windows, or connecting to a database.
- **Target platform:** The Product Owner's local Windows 11 x64 machine; local-first and loopback-only.
- **Branch:** `docs/P6-602-dbeaver-install-e2e`

## 1. Objective

Prepare a narrowly scoped end-to-end test in which the local web app accepts a structured DBeaver Community installation request, produces an evidence-backed immutable proposal, obtains explicit exact-action approval, executes through a fixed backend-owned capability, and independently verifies the result.

The acceptance target is a real installation on the Product Owner's Windows 11 machine after every security and release gate is satisfied. A generated plan or mocked handler is not a successful installation test.

## 2. Product Owner authorization boundary

The Product Owner authorized:
- preparation of the DBeaver test specification;
- implementation work needed to prepare the bounded capability, provided real execution remains disabled until all gates below pass;
- independent A4 review and CI/local verification planning.

This authorization does **not** authorize:
- enabling real execution now;
- bypassing any Phase 6 prerequisite or unresolved security finding;
- installation on any machine other than the explicitly selected local Windows 11 machine;
- administrator elevation, system-wide installation, arbitrary command execution, or a general-purpose package installer;
- database connections, credential entry, JDBC driver downloads, or persistence of database secrets;
- changes to the paused SEC-602-02 workstream unless separately requested.

A separate explicit enablement decision is required after A4 review and evidence are available. The final real installation must also be initiated by the user from the local UI with a fresh approval bound to the exact proposal.

## 3. Input contract and normalization

The supplied JSON is an intent document, not an executable command specification. The backend must parse it into a strict typed request and reject unknown fields, invalid types, overlong values, unsupported platforms, and attempts to supply executable paths, command strings, arbitrary URLs, shell fragments, or handler names.

Normalized initial request:

| Field | Required value |
|---|---|
| Capability | Fixed ID for DBeaver Community installation (new ID to be registered only after policy review) |
| Product | DBeaver Community Edition |
| Platform | Windows 10/11 x64; actual test target must be confirmed as Windows 11 x64 |
| Source preference | Official DBeaver publisher evidence plus WinGet primary discovery |
| Package ID | Candidate `DBeaver.DBeaver.Community`; must be rediscovered and validated at request time |
| Version | Current stable version discovered at request time; no literal placeholder |
| Scope | Per-user, non-elevated installation where supported |
| Workspace | Default under the current user's profile, with canonical path validation |
| JDBC drivers | No automatic driver download during installation; defer until a separate database-specific request |
| Database connection | Out of scope for this installation test |

The client-supplied `command`, `filename`, and URL are never passed to process creation. In particular, the supplied `/S` switch is not accepted as an arbitrary argument. Installer behavior and silent/interactive mode must come from the reviewed fixed adapter and verified package metadata.

## 4. Trusted software discovery

Before an install proposal can be shown, the discovery component must:
1. Confirm the exact edition is Community, not Enterprise.
2. Check the official DBeaver publisher site for product identity, current stable release, and official distribution channels.
3. Search WinGet first and inspect the current manifest for exact package ID, version, publisher, installer URL, SHA-256, architecture, installer type, scope, and signature metadata where available.
4. Verify the installer origin is consistent with the official publisher evidence; disclose redirects and evidence gaps.
5. Compare package version with the current stable publisher release. A stale or mismatched package must not be silently replaced with a direct download.
6. Return VERIFIED CANDIDATE, CONDITIONAL, BLOCKED, or NOT FOUND with source links and checked-at time.

A package identifier remembered in documentation is only a discovery hint, never a permanent allowlist or trust decision. A matching hash and signature are evidence, not a malware-free guarantee.

## 5. Fixed capability and execution boundary

- Register one narrow DBeaver Community install capability; do not turn `software.install` into a generic installer.
- Accept only typed, bounded product/version/architecture/scope fields and immutable discovery evidence.
- Bind approval to a canonical digest of the exact package identity, version, source, installer hash, scope, and fixed execution options.
- Any change to those values invalidates the proposal and requires rediscovery and new approval.
- Dispatch through a fixed code-owned handler/adapter. No model-supplied handler name, command, executable path, URL, script, shell, PowerShell, CMD, BAT, or arbitrary process arguments.
- Use the least-privileged per-user installation supported by the verified package. No automatic elevation or system-wide install.
- Do not execute if the verified installer metadata requires unsupported elevation, scripts, network destinations, or privileges.
- Ensure idempotency: detect an existing installation and produce a safe no-op/already-installed outcome or a separately approved update proposal; never blindly reinstall.
- Record bounded, redacted operational job state and allowlisted audit events only. Never log credentials, raw prompts, or unrestricted machine inventory.

## 6. Configuration and driver handling

The supplied `workspace_path` is a proposed default, not an instruction to create or overwrite arbitrary paths. Resolve the current user's profile from the OS, validate the final canonical path, and use a safe application-specific directory. Do not trust a caller-supplied username or path traversal.

The supplied `drivers_auto_download: true` is not treated as a supported DBeaver installer configuration setting. The installation test must not initiate JDBC driver downloads. Driver Manager use and any database connection are separate future tasks requiring explicit user intent, destination/source checks, and credential-handling review.

## 7. Approval UX

The Thai-first UI must show, before approval:
- DBeaver Community Edition and publisher;
- exact version, x64 architecture, package ID, source, installer origin, hash, signature result, and freshness;
- per-user/non-elevated scope and expected install location;
- whether the operation is install, no-op, or update;
- network destinations and material installer behavior from verified metadata;
- evidence gaps, risks, and the fact that approval authorizes only this exact immutable action.

Approval must be backend-enforced, fresh, single-use, owner/session-bound, action-digest-bound, expiring, replay-resistant, and audited. A frontend button or model response is not authorization.

## 8. Background job lifecycle

Use the approved P6-601 Background Job System. The request returns a Job ID and initial state; the worker uses only the fixed adapter. The lifecycle must distinguish at least QUEUED, STARTING, RUNNING, VERIFYING, SUCCEEDED, FAILED, CANCELLED, and NEEDS_ATTENTION (or the exact canonical states already adopted by the implementation).

Do not retry a side-effecting installation automatically unless idempotency and post-failure state inspection prove that retry cannot duplicate or compound effects. On timeout or worker interruption, inspect actual installation state before proposing another run.

## 9. Independent post-install verification

A run may be marked SUCCEEDED only after independent checks confirm:
- the expected DBeaver Community product identity and version are installed;
- installation location and scope match the approved proposal;
- the installed executable has a valid expected publisher signature where applicable;
- the application starts successfully without requiring elevation;
- no unexpected product edition or unrelated software was installed.

The test must not create a database connection or download JDBC drivers. Those are separate capabilities.

## 10. Security and release gates

Real execution remains disabled until all applicable conditions are evidenced:

1. **Phase 6 prerequisite:** targeted independent A4 review of the merged OIDC + DPAPI/TOTP path and backend-enforced exact-action user presence (F-516-01) is complete and findings are resolved.
2. **Shared security prerequisites:** approval, audit, policy, handler reachability, secret storage/ACL, and background-job integrity controls required by the current Phase 6 threat model are implemented and independently reviewed. Existing SEC-602-02 remains a separate paused workstream; this task must not silently claim it resolved.
3. **Capability-specific design:** threat model, source-discovery contract, privilege/network boundary, failure handling, rollback limitations, and privacy review are complete.
4. **Tests:** strict schema negatives; package ID/version/source/hash/signature mismatch; stale manifest; untrusted redirect; unsupported installer type; elevation required; malicious/extra input; approval digest mutation; wrong owner/session; expired/replayed approval; policy denial; handler drift; audit failure; worker crash/timeout; already-installed/no-op; verification mismatch; zero-execution assertions for every denied path.
5. **Platform evidence:** Windows CI covers native Windows behavior and a dedicated Windows integration environment. Mocks alone are insufficient.
6. **Quality checks:** backend Ruff (including import sorting), backend tests, frontend tests, type/lint checks, CodeQL and relevant Windows CI all complete successfully. Queued/in-progress is not passed.
7. **Independent A4 review:** review exact implementation commit, tests, threat model, CI evidence, and all reachable side effects. No self-approval.
8. **Product Owner enablement:** separate explicit approval to enable this exact capability after review. The user's final real test is performed locally from the UI with exact-action approval.

## 11. Acceptance criteria

- The supplied JSON can be accepted as intent and normalized without executing any field as a command.
- Discovery produces current, evidence-backed DBeaver Community candidate data or a clear BLOCKED/NOT FOUND result.
- The UI displays a precise Thai proposal and exact-action approval.
- Unapproved, altered, stale, mismatched, unauthenticated, or policy-denied requests cannot reach a side-effecting handler.
- Only the fixed DBeaver Community adapter can be invoked for this capability.
- Real installation and independent verification succeed on the Product Owner's Windows 11 x64 machine after all gates and enablement approval.
- No JDBC driver download or database connection occurs in this test.

## 12. Current disposition

**PREPARATION AUTHORIZED; REAL EXECUTION DISABLED.** This document is a capability-specific specification and does not itself satisfy A4, CI, shared security prerequisites, or the separate enablement decision.
