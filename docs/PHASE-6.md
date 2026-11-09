# Phase 6 — Real PC Automation

## Status and authority

**Phase 6 planning AUTHORIZED by the Product Owner on 2026-11-09.**

This is phase-level authorization to begin architecture, requirements, threat analysis, capability decomposition, and test planning. It is **not** blanket authorization to implement or execute any real PC-changing action.

No individual Phase 6 capability is currently authorized. Each capability requires:
1. A bounded task with exact tool ID, parameters, risk classification, permission level, and supported/unsupported behavior.
2. Explicit Product Owner authorization for that capability's runtime implementation.
3. Independent A4 review of the design, threat model, tests, and implementation.
4. Backend-enforced exact-action authorization and user-presence proof, fail-closed behavior, replay/expiry protection, and audit/privacy controls.
5. CI evidence and Product Owner local verification where required.
6. Separate explicit Product Owner approval before merging its runtime PR and before enabling the capability for real execution.

## Objective

Introduce real Windows automation only through narrowly scoped, backend-owned capabilities. Preserve the product's local-first architecture and ensure that model output, frontend state, or a local API token cannot independently authorize machine changes.

## Binding constraints

- Windows 11 local machine only; preserve loopback-only binding and existing Host/Origin/local-token/request-size protections.
- No LAN exposure, public tunnel, cloud-hosted control plane, mobile remote PC control, or remote machine selection.
- All operations pass through a fixed backend-owned tool catalog, strict typed schemas, policy decision, exact-action approval, and a fixed handler map.
- Never execute raw Gemini/model output, arbitrary shell, PowerShell, CMD, scripts, dynamic imports, command strings, or model-supplied handler names.
- No general-purpose terminal, arbitrary command runner, unrestricted filesystem browser/editor, process manager, registry editor, or unrestricted administrator capability.
- Unknown tools, malformed/extra parameters, policy uncertainty, missing authentication, missing user presence, stale/mismatched/replayed approval, handler drift, and audit/policy failure must fail closed.
- Existing `software.install` and `software.remove` handlers remain mock/dry-run until their own capability-specific gates are passed. Phase 6 approval does not switch them to real execution.
- No new provider, provider tool/function calling, external data flow, credential type, or network destination without a separate approved decision.
- Do not persist chat messages, chat history, or task history. Preserve approved in-memory retention limits and audit data minimization; any retention change requires a new Product Owner decision.
- Do not inspect or mutate the user's live PC during planning or tests. Use synthetic fixtures, isolated temporary test directories, mocks, and spy handlers.
- The accepted F-516-01 Phase 5 closeout residual is not a waiver for Phase 6: targeted independent A4 review of the post-implementation Google OIDC + TOTP path and proof of backend-enforced exact-action user presence are prerequisites before any side-effecting capability can be enabled.
- P5-515 Q30 and Q35 remain Partial; do not claim physical-device/screen-reader coverage or runtime sandboxing.
- Branch convention: `<type>/<task-id>-<short-name>`. Thai is the default UI language.

## Capability onboarding model

Every proposed capability must have a separate record containing:

| Field | Required content |
|---|---|
| Stable tool ID | Fixed backend-owned identifier; never a command string |
| Purpose / scope | One narrow outcome and explicit exclusions |
| Inputs | Strict typed schema, bounds, canonicalization, and target binding |
| Risk / permission | Backend-derived R0–R3 and P0–P3 mapping; no client override |
| Preconditions | Exact checks and fail-closed behavior |
| Approval | Human-presence method bound to exact immutable action and parameters |
| Handler | Fixed implementation; no dynamic dispatch or arbitrary command execution |
| Side effects | Explicit files, processes, network destinations, privilege requirements, and rollback limits |
| Privacy / audit | Allowlisted event fields, no secrets/prompts/raw machine inventory, approved retention only |
| Verification | Unit/API/integration tests, negative tests, spy/fake proof, A4 review, CI, local evidence |
| Enablement | Explicit Product Owner authorization and a separate release/enable gate |

No capability may inherit approval from another tool, a prior phase, a successful Dry Run, or a general example in project documents.

## Phase 6 workstreams

| Lane | Responsibility | Boundary |
|---|---|---|
| A1 — Coordinator / Product Analyst | Capability requirements, task breakdown, decision traceability | Cannot approve for the Product Owner |
| A2 — Backend Engineer | Backend-owned policy, authorization, schemas, fixed dispatch, handler isolation | No unrestricted command execution |
| A3 — Frontend / UX Engineer | Thai-first action summary, exact target/parameter review, explicit approval and result states | UI is not the authorization authority |
| A4 — QA / Security Reviewer | Threat model, abuse cases, negative tests, independent review, evidence | Cannot approve or merge its own work |

## Entry conditions and accepted residuals

- Phase 5 closeout is recorded in `docs/P5-519-PHASE-5-CLOSEOUT-REPORT.md`.
- The Product Owner accepted the unperformed targeted A4 review of F-516-01 as a residual for Phase 5 closeout only. Before real execution, A4 must independently review the merged Google OIDC + Windows DPAPI/TOTP implementation, the exact-action step-up binding, bypass resistance, expiry/replay handling, and fail-closed behavior.
- The prior F-516-02 and F-516-03 findings are recorded as resolved by PRs #109 and #108 respectively; Phase 6 review must verify the current merged source rather than rely only on status labels.
- P5-515 residual Q30/Q35 remain visible and are not silently reclassified.

## Initial task — P6-601: Phase 6 capability and execution architecture baseline

**Status: Planning authorized; documentation/review only.**

Deliverables:
1. Read-only source map of current tool catalog, policy decision point, approval API, authenticator step-up, handler registry, audit events, and task result flow. See `docs/P6-601-SOURCE-MAP.md` for the initial source map and A4 review gaps.
2. Threat model for the transition from Dry Run to real side effects, including browser same-origin/script risks, local process risks, parameter substitution, replay, TOCTOU, partial failure, rollback, privilege boundaries, and compromised model/provider output.
3. Capability onboarding template and explicit gate checklist.
4. Dependency plan separating shared authorization hardening from per-capability implementation.
5. A4 review of the Phase 6 architecture baseline and explicit list of unresolved Product Owner decisions.

Exclusions:
- No runtime source changes.
- No real Windows inspection, file/process/registry/network inspection, or machine-changing actions.
- No installer, shell, PowerShell, CMD, script runner, or arbitrary command execution.
- No enabling of existing install/remove tools.
- No new provider/tool-calling/data flow or persistence.

Acceptance criteria:
- All Phase 5 constraints and accepted residuals are represented accurately.
- F-516-01 is a hard precondition for real side-effect enablement, not silently treated as waived.
- Every capability has an independent approval boundary and exact-action contract.
- The architecture rejects arbitrary commands and dynamic handlers by construction.
- Test strategy proves denied/unapproved paths cannot reach side-effect handlers.
- Loopback, authentication, privacy, and data-retention decisions remain unchanged.
- A4 review and Product Owner decisions are recorded before any runtime implementation task is proposed.

## Proposed first capability

The initial capability is **not selected or authorized** by this phase-start decision. Software installation is a possible candidate because `software.install` already has a Dry Run contract, but it is high-risk and must not be assumed approved. A1 should compare candidate capabilities by boundedness, privilege, reversibility, target validation, and verification cost, then present one recommendation with evidence for Product Owner approval.

## Definition of done

- P6-601 architecture and threat model are reviewed by A4.
- Capability onboarding and test gates are documented.
- Residual security prerequisites and open decisions are explicit.
- Product Owner approves each bounded runtime task and each individual capability separately.
- No real PC-changing capability is enabled without its own completed review, tests, CI evidence, and explicit enablement approval.

## Current status / handoff

Phase 6 planning is active. P6-601 is the first bounded task. The next action is a read-only source map and A4 threat review; no live Windows operation is permitted.


## Trusted Software Discovery — planning requirement

Software installation must begin with source discovery and trust assessment, not direct execution of a package-manager command. This is planning only; it does not authorize an installer, package-manager invocation, download, or machine change. The detailed checklist and example are in `docs/P6-601-TRUSTED-SOFTWARE-DISCOVERY.md`.

### Source strategy

| Priority / use | Source | Policy |
|---|---|---|
| Primary Windows package source | WinGet (winget source) | Search first for Windows desktop applications. A catalog hit is a candidate, not proof of safety or publisher endorsement. |
| Vendor-of-record | Official publisher website, documentation, release page, or publisher-controlled repository | Establish product identity, supported versions, official distribution channels, and expected publisher. Cross-check package metadata against it. |
| Secondary Windows source | Chocolatey Community Repository | Consider only when no suitable verified WinGet package exists or the publisher explicitly recommends it. Inspect package scripts and download origin; moderation is a signal, not a guarantee. |
| Developer package source | npm Registry | Use for Node.js libraries and developer tools where appropriate. Verify exact package/scope, repository and publisher links, provenance/integrity, maintainers, dependency tree, and lifecycle scripts. Not a general desktop-app source. |
| Other vendor channel | Microsoft Store or publisher-operated repository | Consider when the publisher identifies it as an official channel and its package identity can be verified. |

### Required discovery and verification workflow

1. Resolve exact product, edition, publisher, platform, architecture, and requested version.
2. Find the publisher's official product/download/documentation page first. Record product identity, publisher, supported Windows version, and distribution channels the publisher documents.
3. Search WinGet first for Windows applications. Record exact PackageIdentifier, source, manifest version, package URL, installer URL, installer type, architecture, scope, version, and SHA-256.
4. Cross-check manifest publisher and installer domain against the publisher's official site. Prefer direct publisher-controlled HTTPS locations; flag redirects, mirrors, URL shorteners, aggregators, and unrelated domains.
5. Verify installer hash and, where applicable, Authenticode signature: signer identity, certificate chain, validity, timestamp, and revocation/status where available. A valid signature proves signer/integrity context, not that software is harmless.
6. Check package freshness against the publisher's current stable release. If the package-manager version lags, is unexpectedly newer, or differs from the official channel, disclose the discrepancy; do not silently substitute another edition/channel.
7. If WinGet has no suitable verified package, evaluate Chocolatey only after reviewing nuspec, install/uninstall scripts, download URLs, checksums, moderation/verification status, and publisher linkage. A moderated community package is not equivalent to a vendor-signed installer.
8. Use npm only for an explicitly requested Node.js package/tool. Check exact package name/scope, metadata, repository/homepage ownership, release provenance or attestations when available, integrity digest, maintainer history, dependency risks, and lifecycle scripts (preinstall/install/postinstall). Lifecycle scripts are executable code and must be disclosed and assessed.
9. Produce a source-evidence report with links, checked-at time, exact version/package identity, publisher match, installer origin, hash/signature findings, freshness, caveats, and confidence. Mark unknown fields unknown; never fabricate evidence.
10. If publisher identity, package identity, download origin, hash, signature, or version cannot be reconciled, mark the candidate BLOCKED. Do not fall back to an arbitrary URL or run a command to test it.

### Trust decision outcomes

- **VERIFIED CANDIDATE** — identity, origin, version, integrity, and signature checks are supported; may be presented for separate install approval.
- **CONDITIONAL** — a bounded evidence gap remains; disclose it and request a Product Owner decision before any install proposal.
- **BLOCKED** — material mismatch, suspicious origin, failed integrity/signature, unknown publisher, or insufficient evidence; no installation proposal.
- **NOT FOUND** — no suitable package in approved sources; report honestly rather than inventing a package ID.

### Example: DBeaver Community

For "install DBeaver", begin at the official DBeaver download/documentation site to distinguish Community from Enterprise and identify the current stable release. Then search WinGet for the exact package ID and inspect the current manifest. The known identifier DBeaver.DBeaver.Community is an example candidate only; revalidate its live manifest and current official release at request time. If the WinGet package is stale or fails publisher/origin checks, disclose that and evaluate an official vendor channel or Chocolatey only if DBeaver itself documents that channel. Do not infer that a package is current merely because it exists in the catalog.

### Later implementation boundary

A future software-install capability must use a fixed backend-owned package-source adapter and typed fields (source enum, exact package ID, exact version, architecture, and approved scope), never free-form command text or model-supplied executable/handler. The discovery report and immutable install proposal must be bound to the exact approval digest. A change to package ID, version, source, installer URL/hash, architecture, scope, or privilege requirement invalidates prior approval and requires new review. Package-manager execution remains disabled until a separate bounded runtime task, F-516-01 A4 prerequisite, independent A4 review, negative tests, CI, and explicit Product Owner enablement approval are complete.

