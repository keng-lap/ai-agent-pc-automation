# P6-601 — A4 Independent QA / Security Review Packet

## Review status and independence

**Status: PREPARED BY A1 / COORDINATOR — INDEPENDENT A4 REVIEW PENDING.**

This packet is not an A4 review, approval, penetration test, or authorization to execute real PC actions. The PR currently has no submitted review records. A4 must independently inspect the exact source/diff and test evidence, record findings and severity, and must not review or approve its own work. No runtime behavior was changed to prepare this packet.

| Field | Value |
|---|---|
| Task | P6-601 |
| Review lane | A4 — QA / Security Reviewer |
| Review baseline | PR #132 head; verify current HEAD before review |
| Scope | Phase 6 safety baseline, trusted software discovery policy, F-516-01 post-implementation review prerequisite, source map |
| Out of scope | Real Windows inspection, package-manager invocation, download, installer execution, or machine mutation |

## Required review inputs

- `docs/PHASE-6.md`
- `docs/P6-601-SOURCE-MAP.md`
- `docs/P6-601-TRUSTED-SOFTWARE-DISCOVERY.md`
- `docs/P5-519-PHASE-5-CLOSEOUT-REPORT.md`
- `docs/P5-516-INDEPENDENT-SECURITY-REVIEW.md`
- `docs/P5-516-01-USER-PRESENCE-DESIGN-DECISION.md`
- Merged implementation and tests from PRs #114–#119 and setup fixes #122–#127
- Current backend sources: `auth_api.py`, `authenticator.py`, `oidc.py`, `step_up.py`, `totp.py`, `plan_api.py`, `audit.py`, `main.py`, `security.py`, `policy.py`, `plans.py`, `tools.py`

## A4 review work packages

### A. F-516-01 post-implementation review — hard prerequisite

Independently verify the implementation against D-P5-516-01 and the merged diff. Do not infer correctness from the Product Owner's local test report.

- OIDC: state/nonce one-time consumption, PKCE S256, token exchange restrictions, ID-token signature, issuer, audience/authorized party, expiry/issued-at, nonce, verified email, stable `sub` allowlist, and rejection of non-owner identities.
- Session: token entropy and digest-only storage, explicit TTL and expiry, logout/revocation, process-restart behavior, cookie attributes, CSRF/Origin interaction, loopback-only callback and middleware boundary.
- Authenticator: trusted enrollment ceremony, one-owner binding, QR/provisioning secret exposure, DPAPI protection, file permissions/atomic writes, corrupted/missing secret handling, no logging of secrets.
- TOTP: RFC profile, clock skew, constant-time comparison, per-step replay, restart behavior, failed-attempt limits, clock rollback, concurrent verification, and atomic consume semantics.
- Step-up: owner + session + plan ID + canonical digest + backend risk binding; challenge TTL; one-time use; expiry, mutation, replay, invalidation, capacity exhaustion, and fail-closed behavior.
- HTTP route wiring: prove the plan routes require authenticated session and that no alternate route can call a side-effect handler without the same backend authorization gate.
- Threat limitation: TOTP is not phishing-resistant and does not protect against a compromised local OS/browser process; ensure documentation does not overstate human-presence assurance.

### B. Approval and execution boundary

- Review `plan_api.py` approval-result cache ordering. It currently returns a cached Dry Run result before rechecking a fresh TOTP challenge. Confirm this is safe only because the current handler is side-effect-free; require a new execution state machine for any future side-effecting handler.
- Review the stale `step_up.py` module docstring that says the store is not wired to the P1 route, while `auth_api.py` constructs it and `plan_api.py` invokes it. Determine whether the discrepancy is documentation-only or signals a test/architecture mismatch.
- Verify every dispatch route reaches the fixed backend-owned handler map and no legacy entry point such as `agent_core.run_agent()` can become a side-effect path without authorization.
- Treat the current in-memory plan/challenge/replay stores as single-process only. No multi-worker or restart-safe guarantee may be claimed.

### C. Audit and failure semantics

- Confirm current `record_optional_audit_event` is best-effort/fail-open and `auth_audit` is bounded/process-local; neither is a durable security ledger.
- Determine which events must be mandatory before any side-effecting capability (proposal, approval, execution-start, success/failure, rollback/partial result, denial).
- Specify whether audit write failure must block a side effect; Phase 6 baseline says policy/audit failure must fail closed, so identify the required implementation delta and tests.
- Verify data minimization: no prompt, TOTP, QR/provisioning URI, secret, raw command, raw package script, or unnecessary machine inventory in audit records.

### D. Trusted Software Discovery threat model

Review the source hierarchy and evidence model for WinGet primary, Chocolatey secondary, npm only for Node.js packages/tools, and publisher official site as vendor-of-record.

- Package identity: typosquatting, lookalike IDs, Community/Enterprise confusion, namespace takeover, publisher mismatch, package replacement, and stale catalog entries.
- Source integrity: manifest/source trust, repository revision, installer URL redirects, CDN or mirror changes, HTTPS downgrade, hash mismatch, Authenticode signer mismatch, expired/revoked/untrusted certificates, and unsigned installers.
- Freshness and TOCTOU: package/version/manifest or installer changes between discovery and execution; approval must bind immutable evidence including source, exact package ID, version, architecture, scope, manifest revision/hash, installer URL and SHA-256, signer identity, and risk/privilege attributes. Re-fetch and compare immediately before execution; any mismatch invalidates approval.
- Chocolatey: nuspec and PowerShell install/uninstall scripts are executable code; moderation is not a guarantee. Require script review and exact download/checksum binding.
- npm: package scope/name confusion, maintainer/account compromise, dependency takeover, transitive dependency risk, provenance/integrity, and lifecycle scripts. Lifecycle scripts must be disabled by default or separately disclosed and explicitly approved; `npm install` is not a passive download.
- User approval: show product/edition, publisher, source, exact version, architecture, scope, privilege needs, installer domain, hash/signature findings, dependencies/scripts, and uncertainty. Approval must be bound to the exact evidence digest.
- Fail closed: unknown publisher, conflicting metadata, unavailable evidence, hash/signature mismatch, unexpected redirects, unsupported installer type, stale manifest, or unresolved risk must block installation; no automatic fallback to arbitrary URLs.

## Coordinator preliminary observations — not A4 findings

These are review prompts from the source map, not independent conclusions:

1. `plan_api.py` checks `_approval_results` before requiring/verifying a new step-up challenge. Current impact is limited to returning a cached Dry Run result; the same ordering must not be copied into a real execution path.
2. `step_up.py` module documentation says the store is not wired to the P1 route, but the current auth and plan API code does wire it. Reconcile the comment with actual tests/source.
3. The generic audit sink is optional and fail-open; this does not meet a mandatory fail-closed execution ledger requirement.
4. The step-up challenge, TOTP replay guard, session store, plan store, and approval cache are process-local. Multi-worker operation and robust restart continuity are not supported.
5. Session cookie is HttpOnly and SameSite=Lax but `Secure=False` for the current loopback HTTP callback. A4 must assess the local threat model and whether the documented deployment assumptions adequately constrain this choice.
6. Trusted software discovery is not implemented in runtime. Current plans explicitly carry source-not-checked state; package-manager metadata must never be inferred from the user's free-text program target.

## Required A4 deliverable

A4 must publish a separate review report with:

- Exact commit SHA and files/diffs reviewed.
- Test commands, CI run/job links, actual results, and checks not run.
- Threat-to-control-to-test traceability.
- Findings with ID, severity, affected code, exploit preconditions, impact, reproduction or rationale, and required remediation.
- Explicit assessment of F-516-01; no implicit pass from Phase 5 closeout.
- Explicit disposition of approval cache/idempotency, stale step-up docstring, audit fail-open behavior, process-local state, and Trusted Software Discovery TOCTOU.
- A clear conclusion: PASS WITH LIMITATIONS / CHANGES REQUIRED / BLOCKED. A4 must not authorize Product Owner scope or merge.

## Acceptance gate

P6-601 cannot be marked complete and no side-effecting capability may be proposed for implementation until the independent A4 report is recorded and all blocking findings are fixed or explicitly dispositioned by the Product Owner. This packet itself does not satisfy that gate.