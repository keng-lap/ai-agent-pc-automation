# P5-516 — Independent Security Review and Phase 5 Evidence Pack

## Review record

| Field | Value |
|---|---|
| Task | P5-516 / I7 |
| Review lane | A4 — QA / Security Reviewer |
| Review date | 2026-11-08 |
| Repository baseline | `main` — `b4136b9c2fedb3ca544a920b8106f87b62639ea3` |
| Review type | Read-only source, merged-diff, test, threat-model, and CI evidence review |
| Scope | P5-510 through P5-515, plus the separately approved P5-517 approval-gated P1 Dry Run implementation in merged PR #99 |
| Changes made by this review | Documentation only; no runtime code or tests changed |

This is an internal A4 review against the implementation lane. It is not an external penetration test, third-party certification, or proof against a compromised local OS account/browser extension. No local Windows host was inspected and no live exploit or machine-changing action was attempted.

## Executive result

**No direct route to a real Windows machine-changing operation was identified in the reviewed `main` source.** The registered handlers remain fixed mock/dry-run functions. Backend policy, strict request models, plan integrity, expiry, replay handling, and local HTTP boundary controls are present and supported by tests.

Three residual findings are recorded below. They do not provide a current real-PC execution path, but they must remain visible. In particular, P5-517 approval is a local UI/API workflow, not strong proof of human identity; the audit sink has no runtime event producers; and a legacy internal orchestration function can still invoke a dry-run without going through the new approval route if it is ever reused.

**Review disposition:** P5-516 review and evidence pack are complete with findings explicitly documented. The findings are not represented as fixed. Phase 6 and real PC execution remain unauthorized.

## Review coverage

### Source and architecture

Reviewed the current source for:

- Backend startup, configuration, loopback binding, local token, Host/Origin, JSON content-type, and request-size enforcement.
- Backend-owned R0–R3 / P0–P3 policy, immutable catalog, typed deny outcomes, and final fixed-handler dispatch.
- Strict tool request/result schemas and the absence of arbitrary command, shell, dynamic import, process, filesystem, registry, or package-manager handlers.
- Immutable plan schema, canonical digest, ten-minute expiry, process-restart invalidation, clock rollback behavior, bounded plan capacity, and approval-result replay cache.
- P1 approval API, deterministic plan creation/refinement, clarification blocking, per-program dry-run dispatch, and the Angular approval control.
- Ephemeral audit event schema/sink, Gemini key handling, in-memory conversation retention, safe error responses, and frontend storage behavior.

### Merged changes and evidence

Reviewed the merged implementation and verification increments:

- P5-510–P5-514: PRs #58, #61, #63, #64, and #65.
- P5-517 approval-gated P1 Dry Run: PR #99.
- P5-515 verification increments: PRs #66, #73, #74, #75, #77, #81, #82, #84, #85, and #104.
- P5-515 closeout evidence: PR #106.

The review also checked the governing threat model, approved P5-508 decisions (including D-P5-13), P5-509 task breakdown, P5-515 traceability matrix, verification evidence, A4 review, and closeout report.

### CI evidence

- PR #104 CI run #42395817656 recorded 257 backend tests, Ruff, 36 frontend unit tests, 9 Playwright E2E tests, and frontend build as passed. Mobile cases are Chromium viewport emulation only.
- Final `main` CI run #42399589297 on merge commit `b4136b9` completed with conclusion `success`.
- The final main run's backend job passed the backend test and Ruff steps. Its frontend job passed frontend unit tests, Playwright desktop/mobile viewport E2E, and frontend build.

The GitHub run metadata establishes successful step conclusions. This review does not claim that the reviewer independently ran those tests on the user's Windows machine.

## Findings

### F-516-01 — P1 approval does not prove human presence

**Severity: Medium — residual limitation; must be addressed before any machine-changing capability.**

The approval endpoint accepts an empty, strict request body and identifies the plan by its server-generated plan ID. The middleware requires the local API token and an allowed Origin for state-changing requests. This prevents ordinary cross-origin browser requests, but the token is injected by the local development proxy and is not a human identity or user-presence signal. A same-origin script or sufficiently privileged browser extension able to drive the local UI/API can submit the approval request through that proxy without proving that the owner personally clicked the control.

This limitation is consistent with the threat model's statement that the local token is not human identity or proof of consent. Current impact is bounded because the only registered handlers are mock/dry-run and no Windows change occurs.

**Required future disposition:** before Phase 6 or any side-effecting capability, define and implement a separate user-presence/authorization control bound to the exact action. Do not treat the local API token, Origin header, or plan ID alone as proof of human approval.

### F-516-02 — Ephemeral audit sink has no runtime event producers

**Severity: Medium — evidence/observability gap.**

The bounded `AuditEventSink`, event schema, and helper are implemented and unit-tested. Repository source search found no runtime imports or call sites from the application, policy, plan API, or dispatch path. The event types therefore are not emitted during ordinary application operation. Tests prove the sink's schema, capacity, restart/clear behavior, and optional-failure behavior in isolation; they do not prove that real application events are recorded.

The approved option A correctly avoids durable storage and external telemetry, but the current runtime has no usable in-memory security-event trail.

**Required future disposition:** the Product Owner should decide whether the intended P1 behavior is (a) no event collection, or (b) bounded in-memory events with explicit producers for the approved event types. Any integration must preserve the allowlist, data minimization, non-blocking optional diagnostics, and no durable persistence. Resolve this before claiming operational audit coverage or expanding capabilities.

### F-516-03 — Legacy internal Agent entry point bypasses the P1 approval workflow

**Severity: Medium — dormant path; no current HTTP route found.**

`agent_core.run_agent()` still selects and validates a tool, checks policy, and calls `execute_tool()` directly. It does not require a P5-517 plan ID or the explicit approval transition. Repository search found no current production route importing or calling this function; current chat/plan API flow uses the separate plan API. The path is exercised by tests, not exposed as a current HTTP endpoint.

If a future route or runtime component reuses `run_agent()`, it can invoke the mock Dry Run without the explicit P1 approval gate required by D-P5-13. This does not currently enable real PC changes, but it is an unsafe integration seam.

**Required future disposition:** before reusing or exposing this function, refactor it to return a plan only or require a server-validated approved-plan reference. Add a regression test proving no handler is called through any unapproved entry point. Do not rely on the absence of a current route as a permanent safety control.

### F-516-04 — Documentation drift outside the docs-only review scope

**Severity: Low.**

The current `README.md` root file still describes P5-515 as in progress and P5-516 as gated. `docs/PROJECT.md` also retained an older statement that Phase 5 runtime implementation was not authorized. The P5-517 implementation's `plan_api.py` module docstring still says Gemini contributes validated display-only plan text, while the current implementation creates the trusted plan deterministically in the backend without a second Gemini call.

This PR reconciles the Phase 5 task and project documents under `docs/`. The root `README.md` and runtime source docstring are intentionally not changed in this documentation-only review.

**Required future disposition:** synchronize the root README and correct the stale source docstring in a separately authorized change.

## Controls found satisfactory within the reviewed scope

- Backend binds only to loopback addresses; non-loopback configuration is rejected.
- API requests require exactly one local token, compared in constant time. Host and Origin are allowlisted; state-changing requests require Origin and JSON; bodies are bounded to 16 KiB.
- Tool catalog and handler mapping are backend-owned and fixed. Tool/request/result models reject extra fields and invalid types.
- Policy configuration is validated at startup and before dispatch. Unknown, denied, or inconsistent policy does not reach a handler. Handler identity is checked at the dispatch boundary.
- Plan content is immutable, digest-checked, bounded, expires after ten minutes, and is invalidated by restart or detected clock rollback.
- P5-517 creates plans without dispatch, requires the approval route for its current API flow, blocks plans needing clarification, dispatches each listed program through fixed dry-run handlers, and caches replay results.
- Current handlers only return dry-run results. No arbitrary shell, PowerShell, CMD, process, filesystem, registry, package-manager, installer, or real machine-changing handler was found.
- Gemini key is held in backend process memory; conversation context is bounded in process memory and is not written to durable chat/task history. Provider data transfer is limited to the separately approved Gemini chat flow.
- Error responses are bounded and do not return raw exception messages or stack traces.

## Known limitations and exclusions

- Q30 remains Partial: physical iPhone and screen-reader testing was deferred by the Product Owner; Chromium viewport emulation is not physical-device or assistive-technology evidence.
- Q35 remains Partial: static capability checks are not a runtime sandbox.
- The review did not perform third-party penetration testing, fuzzing against a live deployment, local Windows execution, or exploit testing against browser extensions/local processes.
- No Windows host inspection, shell command, installer, filesystem mutation, process action, network-setting change, or real machine-changing action was performed.
- P2 inspection and P3 execution remain denied. Phase 6 remains not started and unauthorized.

## Final A4 conclusion

The reviewed implementation preserves the declared local-first, dry-run-only boundary for the current exposed application flow. No direct machine-changing path was identified. The three Medium findings above are documented residuals, not fixed defects; they must be addressed or explicitly dispositioned before any expansion toward real execution. The low-severity documentation drift is partially reconciled in this review PR.

**P5-516 review deliverable: complete — findings and limitations recorded.**
**Phase 6 / real PC execution: NOT AUTHORIZED.**
